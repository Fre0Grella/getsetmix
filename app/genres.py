"""The genre list the app offers and `genre.map` maps onto.

It lives on the server so the UI and the cleanup rules share one list. The UI
reads it from `GET /api/library/rules`.
"""
from __future__ import annotations

GENRES: tuple[str, ...] = (
    "Afro House", "Amapiano", "Bass House", "Big Room", "Breakbeat", "Dance",
    "Deep House", "Disco", "Drum & Bass", "Dubstep", "EDM", "Electro", "Funk",
    "Future House", "Garage", "Hard Rock", "Hard Techno", "Hardcore", "Hardstyle",
    "Heavy Metal", "Hip-Hop", "House", "Indie Dance", "Italo Disco", "Jungle",
    "Latin", "Mainstage", "Melodic House & Techno", "Minimal", "Moombahton",
    "Pop", "Progressive House", "Psytrance", "R&B", "Reggaeton", "Rock",
    "Tech House", "Techno", "Trance", "Trap", "Tropical House", "UK Garage",
)

# Quick picks under an open row's genre field, after the ones the list already uses.
GENRE_PICKS: tuple[str, ...] = (
    "House", "Tech House", "Techno", "Afro House", "Melodic House & Techno", "Drum & Bass",
)
