"""Lazy Korean spacing and typo correction for real-time chat."""

from __future__ import annotations
from .corpus_typo_corrector import correct as corpus_correct

import os
import re
import sys
import threading
from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

DOMAIN_TYPO_PATTERNS = (
    # 장르 및 조사 오타
    (r"애닌(?=\s|$|[,.!?]|보고)", "애니메이션은 "),
    (r"애니를?은", "애니메이션은"),
    (r"에니메이션", "애니메이션"),

    # 배우 문맥 오타
    (r"나온느", "나오는"),
    (r"나오느", "나오는"),
    (r"나오눈", "나오는"),
    (r"별도다", "별로다"),
    (r"별도야", "별로야"),
    (r"조은데", "좋은데"),
    (r"안조아", "안 좋아"),
    (r"가조아", "가 좋아"),
    (r"보고시퍼", "보고 싶어"),
    (r"보고시픔", "보고 싶음"),
    (r"조켓어", "좋겠어"),
    (r"가입햇음", "가입했음"),
    (r"싶지안아", "싶지 않아"),
    (r"([가-힣]{2,5})(나오는|감독)", r"\1 \2"),
    (r"(배우가|감독이)(나오는|만든)", r"\1 \2"),

    # OTT 축약어
    (r"넷플이랑", "넷플릭스랑"),
    (r"넷플로", "넷플릭스로"),
    (r"티빙가입", "티빙 가입"),

    # 부정 및 띄어쓰기
    (r"보고\s*싶지\s*않", "보고 싶지 않"),
    (r"보고싶지\s*않", "보고 싶지 않"),
)


def _normalize_domain_typos(text: str) -> str:
    normalized = text

    for pattern, replacement in DOMAIN_TYPO_PATTERNS:
        normalized = re.sub(
            pattern,
            replacement,
            normalized,
            flags=re.IGNORECASE,
        )

    return re.sub(r"\s+", " ", normalized).strip()


@dataclass(frozen=True)
class CorrectionResult:
    original: str
    corrected: str
    spacing_applied: bool = False
    typo_applied: bool = False
    backend: str = "rule-fallback"


class KoreanTextCorrector:
    """Runs ElectraSpacer -> ET5 once per unique sentence, with safe fallback."""

    def __init__(
        self,
        *,
        hf_token: str | None,
        typo_model_name: str,
        spacer_dir: Path,
        use_typo_model: bool,
        use_spacer_model: bool,
        max_chars: int = 180,
    ) -> None:
        self.hf_token = (hf_token or "").strip() or None
        self.typo_model_name = typo_model_name
        self.spacer_dir = spacer_dir.resolve()
        self.use_typo_model = use_typo_model
        self.use_spacer_model = use_spacer_model
        self.max_chars = max_chars
        self._spacer = None
        self._typo_tokenizer = None
        self._typo_model = None
        self._lock = threading.RLock()
        self.errors: dict[str, str] = {}

        if self.hf_token:
            os.environ.setdefault("HF_TOKEN", self.hf_token)

    
    @staticmethod
    def _safe(original: str, candidate: str) -> bool:
        candidate = re.sub(r"\s+", " ", candidate).strip()

        if not candidate:
            return False

        if len(candidate) > max(16, int(len(original) * 1.8)):
            return False

        left = re.sub(r"\s+", "", original)
        right = re.sub(r"\s+", "", candidate)

        similarity = SequenceMatcher(None, left, right).ratio()

        return similarity >= 0.55
    
    @staticmethod
    def _needs_typo_model(original: str, spaced: str) -> bool:
        """Run ET5 only when the chat text looks typo-like.

        Normal short chat sentences should bypass the heavy model.
        """

        text = (spaced or original).strip()

        if not text:
            return False

        compact_length = len(re.sub(r"\s+", "", text))

        # 긴 문장은 실시간 ET5 대상에서 제외
        if compact_length > 40:
            return False

        typo_patterns = (
            # 좋아 / 싫어 계열
            r"조아",
            r"죠아",
            r"좋앙",
            r"실어",
            r"시러",
            r"실음",

            # 보고 싶다 계열
            r"보구",
            r"십따",
            r"십어",
            r"시퍼",
            r"시픔",

            # 흔한 채팅 오타
            r"재밋",
            r"잼잇",
            r"잼있",
            r"업서",
            r"엄서",
            r"안조",
            r"조은",
        )

        return any(
            re.search(pattern, text)
            for pattern in typo_patterns
        )

    def _load_spacer(self):
        if self._spacer is not None or not self.use_spacer_model:
            return self._spacer
        try:
            model_dir = self.spacer_dir / "model"
            if not (model_dir / "models" / "pytorch_model.bin").exists():
                raise FileNotFoundError(f"ElectraSpacer weights not found: {model_dir}")
            for path in (str(model_dir), str(self.spacer_dir)):
                if path not in sys.path:
                    sys.path.insert(0, path)
            previous = Path.cwd()
            try:
                os.chdir(model_dir)
                from spaceprediction import ElectraSpacer
                self._spacer = ElectraSpacer(max_len=256)
            finally:
                os.chdir(previous)
        except Exception as exc:  # optional model must not break chat
            self.errors["spacing"] = f"{type(exc).__name__}: {exc}"
            self.use_spacer_model = False
        return self._spacer

    def _load_typo_model(self):
        if self._typo_model is not None or not self.use_typo_model:
            return self._typo_tokenizer, self._typo_model
        try:
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
            kwargs = {"token": self.hf_token} if self.hf_token else {}
            self._typo_tokenizer = AutoTokenizer.from_pretrained(
                self.typo_model_name, **kwargs
            )
            self._typo_model = AutoModelForSeq2SeqLM.from_pretrained(
                self.typo_model_name, **kwargs
            ).to("cpu")
            self._typo_model.eval()
        except Exception as exc:
            self.errors["typo"] = f"{type(exc).__name__}: {exc}"
            self.use_typo_model = False
        return self._typo_tokenizer, self._typo_model

    @lru_cache(maxsize=2048)
    def correct(self, text: str) -> CorrectionResult:
        original = re.sub(r"\s+", " ", text).strip()
        if len(original) < 3 or len(original) > self.max_chars:
            return CorrectionResult(original, original)

        with self._lock:
            current = original
            
            spacing_applied = False
            typo_applied = False
            backends: list[str] = []
            corpus_candidate = corpus_correct(current)

            if self._safe(current, corpus_candidate):
                if corpus_candidate != current:
                    current = corpus_candidate
                    typo_applied = True
                    backends.append("corpus-rules")

            spacer = self._load_spacer()
            if spacer is not None:
                try:
                    previous = Path.cwd()
                    try:
                        # The upstream implementation resolves ./results and
                        # ./models during prediction, not only during loading.
                        os.chdir(self.spacer_dir / "model")
                        candidate = spacer(current)
                    finally:
                        os.chdir(previous)
                    if self._safe(current, candidate):
                        current = re.sub(r"\s+", " ", candidate).strip()
                        spacing_applied = current != original
                        backends.append("electra-spacer")
                except Exception as exc:
                    self.errors["spacing_inference"] = f"{type(exc).__name__}: {exc}"

            tokenizer = model = None

            rule_applied = "corpus-rules" in backends or "domain-rules" in backends

            if (
                not rule_applied
                and self._needs_typo_model(original, current)
            ):
                tokenizer, model = self._load_typo_model()

            if tokenizer is not None and model is not None:

                try:
                    encoded = tokenizer(
                        "맞춤법을 고쳐주세요: " + current,
                        return_tensors="pt",
                        truncation=True,
                        max_length=192,
                    )
                    generated = model.generate(
                        **encoded,
                        max_new_tokens=128,
                        num_beams=2,
                        early_stopping=True,
                    )
                    candidate = tokenizer.decode(generated[0], skip_special_tokens=True)
                    if self._safe(current, candidate):
                        typo_applied = candidate.strip() != current
                        current = candidate.strip()
                        backends.append("et5-typos-corrector")
                except Exception as exc:
                    self.errors["typo_inference"] = f"{type(exc).__name__}: {exc}"

            domain_corrected = _normalize_domain_typos(current)

            if domain_corrected != current:
                current = domain_corrected
                typo_applied = True
                backends.append("domain-rules")
            return CorrectionResult(
                original=original,
                corrected=current,
                spacing_applied=spacing_applied,
                typo_applied=typo_applied,
                backend="+".join(backends) or "rule-fallback",
            )

    def status(self) -> dict:
        return {
            "spacing_enabled": self.use_spacer_model,
            "spacing_loaded": self._spacer is not None,
            "typo_enabled": self.use_typo_model,
            "typo_loaded": self._typo_model is not None,
            "typo_model": self.typo_model_name,
            "hf_token_configured": bool(self.hf_token),
            "cache_entries": self.correct.cache_info().currsize,
            "errors": self.errors,
        }
