"""The same-song rules (app/matching.py), with the real-world cases that shaped them."""
from app.matching import comment_source, norm_url, same_song, tokens


def song(name: str, artist: str = "", url: str = "") -> dict:
    return {"name": name, "artist": artist, "url": norm_url(url)}


def test_same_source_url_whatever_the_tags():
    a = song("Renamed", "Someone", "https://youtu.be/abc/")
    b = song("Test Track", "Tester", "HTTPS://youtu.be/abc")
    assert same_song(a, b)


def test_title_and_artist_ignore_platform_noise():
    assert same_song(song("Test Track (Official Video) [HD]", "Tester"),
                     song("Test Track", "Tester"))


def test_distinct_mixes_are_not_the_same_song():
    # Extended Mix vs Radio Edit are different tracks for a DJ.
    assert not same_song(song("Night Drive (Radio Edit)", "DJ A"),
                         song("Night Drive (Extended Mix)", "DJ A"))


def test_new_song_is_not_a_match():
    assert not same_song(song("Brand New", "Nobody", "https://x/y"),
                         song("Test Track", "Tester"))


def test_artist_punctuation_differs():
    assert same_song(song("Shake That Bunda", "Fantasm, The Straikerz"),
                     song("Shake That Bunda", "Fantasm & The Straikerz"))


def test_extra_artist_and_version_suffix():
    assert same_song(song("Hardtechno Tacata", "Dustin Hertz, Tiago Garcia-Arenas"),
                     song("Hardtechno Tacata (Extended)", "Dustin Hertz"))


def test_remix_with_fewer_artists():
    assert same_song(
        song("Woops (Dimitri Vegas & Junkie Kid Remix)",
             "Bountyhunter, Dimitri Vegas, Junkie Kid, Stefan Melis"),
        song("Woops (Dimitri Vegas & Junkie Kid Remix)", "Bountyhunter, Dimitri Vegas & Junkie Kid"))


def test_single_word_title_needs_exact_match():
    # "Go" is not "Go Hard".
    assert not same_song(song("Go", "Same Artist"), song("Go Hard", "Same Artist"))


def test_shared_word_is_not_a_duplicate():
    # "Hardtechno Tacata" must not match the unrelated "Tacata' OFFICIAL VIDEO".
    assert not same_song(song("Hardtechno Tacata", "Dustin Hertz, Tiago Garcia-Arenas"),
                         song("Tacata' OFFICIAL VIDEO", "Tacabro"))


def test_an_artist_on_one_side_only_is_not_a_match():
    assert not same_song(song("Test Track", "Tester"), song("Test Track"))
    assert same_song(song("Test Track"), song("Test Track"))


def test_comment_source_reads_what_the_tagger_writes():
    assert comment_source("Source: https://youtu.be/abc | via GetSetMix") == "https://youtu.be/abc"
    assert comment_source("my notes; source: https://x/y; more") == "https://x/y"
    assert comment_source("no link here") == ""


def test_tokens_are_ascii_words():
    assert tokens("Café del Mar (Official Audio) ft. Ü") == frozenset({"caf", "del", "mar"})
