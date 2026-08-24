from meetup_ml.person_identity import canonical_person_name


def test_korean_and_english_person_names_match():
    assert canonical_person_name("류준열") == canonical_person_name("Ryu Jun-yeol")
    assert canonical_person_name("혜리") == canonical_person_name("Lee Hye-ri")
    assert canonical_person_name("봉준호") == canonical_person_name("Bong Joon-ho")
