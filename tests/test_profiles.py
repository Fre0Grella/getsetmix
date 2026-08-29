"""Library-relative path mapping: the server's path space vs each DJ machine's."""
from app.profiles import (
    Profile,
    join_relative,
    location_uri,
    normalize_os,
    path_from_location,
    slugify,
    to_relative,
    unique_id,
)

WIN = Profile(id="studio", name="Studio PC", os="windows",
              library_root="C:\\Users\\marco\\Nextcloud\\Music")
MAC = Profile(id="mbp", name="MacBook", os="macos",
              library_root="/Users/marco/Music")


def test_maps_server_path_onto_windows_machine():
    path, mapped = WIN.map_path("/music/Hardstyle/Artist - Title.mp3", "/music")
    assert mapped
    assert path == "C:\\Users\\marco\\Nextcloud\\Music\\Hardstyle\\Artist - Title.mp3"


def test_maps_server_path_onto_macos_machine():
    path, mapped = MAC.map_path("/music/Hardstyle/Artist - Title.mp3", "/music")
    assert mapped and path == "/Users/marco/Music/Hardstyle/Artist - Title.mp3"


def test_windows_location_uri_keeps_leading_slash():
    """Without the leading slash Rekordbox reads the drive letter as a host."""
    loc = WIN.location_for("/music/a b.mp3", "/music")
    assert loc == "file://localhost/C:/Users/marco/Nextcloud/Music/a%20b.mp3"
    assert path_from_location(loc) == "C:/Users/marco/Nextcloud/Music/a b.mp3"


def test_file_outside_library_root_is_reported_unmapped():
    path, mapped = WIN.map_path("/elsewhere/x.mp3", "/music")
    assert not mapped and path == "/elsewhere/x.mp3"


def test_profile_without_root_is_unmapped():
    bare = Profile(id="x", os="windows")
    assert bare.map_path("/music/a.mp3", "/music") == ("/music/a.mp3", False)


def test_trailing_separator_on_root_is_tolerated():
    assert to_relative("/music/x/y.mp3", "/music/") == "x/y.mp3"
    assert to_relative("/music/x/y.mp3", "/music") == "x/y.mp3"


def test_nested_relative_path_survives_the_round_trip():
    rel = to_relative("/music/a/b/c.mp3", "/music")
    assert join_relative("D:\\DJ", rel, "windows") == "D:\\DJ\\a\\b\\c.mp3"
    assert join_relative("/srv/dj", rel, "linux") == "/srv/dj/a/b/c.mp3"


def test_root_itself_maps_to_empty_relative():
    assert to_relative("/music", "/music") == ""


def test_sibling_directory_is_not_treated_as_inside_root():
    """'/music-old/x' must not be read as being under '/music'."""
    assert to_relative("/music-old/x.mp3", "/music") is None


def test_windows_root_matching_is_case_insensitive():
    p = Profile(id="w", os="windows", library_root="C:\\Music")
    assert to_relative("c:\\music\\a.mp3", "C:\\Music", "windows") == "a.mp3"
    assert p.os == "windows"


def test_dj_xml_path_defaults_into_the_library_so_it_syncs():
    assert WIN.dj_xml_path() == "C:\\Users\\marco\\Nextcloud\\Music\\getsetmix-studio.xml"
    assert MAC.dj_xml_path() == "/Users/marco/Music/getsetmix-mbp.xml"


def test_explicit_xml_path_wins():
    p = Profile(id="x", os="linux", library_root="/m", xml_path="/tmp/mine.xml")
    assert p.dj_xml_path() == "/tmp/mine.xml"


def test_public_dict_hides_the_agent_token():
    p = Profile(id="x", agent_token="secret", library_root="/m")
    pub = p.public()
    assert "agent_token" not in pub and pub["paired"] is True


def test_os_normalisation():
    assert normalize_os("Darwin") == "macos"
    assert normalize_os("Win32") == "windows"
    assert normalize_os("") == "linux"


def test_slug_and_unique_id():
    assert slugify("Marco's Studio PC!") == "marco-s-studio-pc"
    assert unique_id("Studio", ["studio"]) == "studio-2"
    assert unique_id("Studio", ["studio", "studio-2"]) == "studio-3"


def test_location_uri_quotes_non_ascii():
    loc = location_uri("/music/Björk – Jóga.mp3", "linux")
    assert " " not in loc and loc.startswith("file://localhost/music/")
