from pathlib import Path

from meetup_ml.corpus_typo_corrector import correct as corpus_correct
from meetup_ml.text_correction import KoreanTextCorrector


text = "오늘 영화 보구십따"

print("1. ORIGINAL =", text)

candidate = corpus_correct(text)
print("2. CORPUS   =", candidate)

corrector = KoreanTextCorrector(
    hf_token=None,
    typo_model_name="j5ng/et5-typos-corrector",
    spacer_dir=Path("vendor/ElectraSpacer"),
    use_typo_model=True,
    use_spacer_model=False,
)

print("3. SAFE     =", corrector._safe(text, candidate))

result = corrector.correct(text)

print("4. METHOD   =", result.corrected)
print("5. BACKEND  =", result.backend)
print("6. ERRORS   =", corrector.errors)