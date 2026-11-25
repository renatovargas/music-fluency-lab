from mfl.theory import matches_chord, voice_leading_distance, note_name

def test_chord_inversions():
    assert matches_chord({60, 64, 67}, "C")
    assert matches_chord({64, 67, 72}, "C")
    assert matches_chord({60, 64, 69}, "Am")
    assert not matches_chord({60, 64, 67, 72}, "C")
    assert not matches_chord({60, 64, 68}, "C")

def test_distance():
    assert voice_leading_distance({60,64,67}, {60,64,69}) == 2
    assert note_name(60) == "C4"
