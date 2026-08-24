from pathlib import Path

from meetup_ml.text_correction import KoreanTextCorrector


def make_corrector():
    return KoreanTextCorrector(
        hf_token=None,
        typo_model_name="j5ng/et5-typos-corrector",
        spacer_dir=Path("vendor/ElectraSpacer"),
        use_typo_model=False,
        use_spacer_model=False,
    )


def test_domain_typo_rules():
    corrector = make_corrector()

    assert (
        corrector.correct("애닌보고싶지안아").corrected
        == "애니메이션은 보고 싶지 않아"
    )