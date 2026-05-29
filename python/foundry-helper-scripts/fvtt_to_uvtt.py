#!/usr/bin/env python3
"""Convert a Foundry VTT scene JSON export to a Universal VTT (.dd2vtt) file
that the Draw Steel Codex / DMHub importer can consume."""

from __future__ import annotations

import argparse
import base64
import io
import json
import logging
import math
import os
import struct
import sys
import urllib.parse
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

try:
    from PIL import Image  # type: ignore
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False


logger = logging.getLogger(__name__)


DMHUB_MAX_IMAGE_SIZE = 8192


# Foundry wall constants -> human-readable names for reports and metadata.
SENSE_NAMES = {
    0: "None",
    10: "Limited",
    20: "Normal",
    30: "Proximity",
    40: "Distance",
}
DOOR_NAMES = {0: "Wall", 1: "Door", 2: "SecretDoor"}
DIRECTION_NAMES = {0: "Both", 1: "Left", 2: "Right"}
DOOR_STATE_NAMES = {0: "Closed", 1: "Open", 2: "Locked"}


def as_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def sense_name(v: Any) -> str:
    if v is None:
        return "None"
    return SENSE_NAMES.get(as_int(v), str(v))


def door_name(v: Any) -> str:
    return DOOR_NAMES.get(as_int(v), str(v))


def direction_name(v: Any) -> str:
    return DIRECTION_NAMES.get(as_int(v), str(v))


def door_state_name(v: Any) -> str:
    return DOOR_STATE_NAMES.get(as_int(v), str(v))


def wall_int(w: Dict[str, Any], key: str, default: int) -> int:
    value = as_int(w.get(key), default)
    return default if value is None else value


class ImageEncodeError(Exception):
    pass


class ResolvedImage(NamedTuple):
    path: Path
    source: str
    target_w_px: Optional[float] = None
    target_h_px: Optional[float] = None
    origin_x_px: Optional[float] = None
    origin_y_px: Optional[float] = None


IMAGE_SUFFIXES = {".apng", ".gif", ".jpeg", ".jpg", ".png", ".webp"}


def as_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def load_scene(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def is_remote_src(src: str) -> bool:
    return src.startswith("http://") or src.startswith("https://")


def is_image_src(src: str) -> bool:
    path = urllib.parse.urlparse(urllib.parse.unquote(src)).path
    return Path(path).suffix.lower() in IMAGE_SUFFIXES


def image_path_candidates(src: str, foundry_data: Optional[Path],
                          scene_path: Path) -> List[Path]:
    src = urllib.parse.unquote(src)
    src_path = Path(os.path.expanduser(src))

    candidates: List[Path] = []
    if src_path.is_absolute():
        candidates.append(src_path)
    if foundry_data is not None:
        candidates.append(foundry_data / src_path)
        candidates.append(foundry_data / "Data" / src_path)
    candidates.append(scene_path.parent / src_path)
    candidates.append(scene_path.parent / src_path.name)

    return candidates


def resolve_image_src(src: str, foundry_data: Optional[Path],
                      scene_path: Path, warn_missing: bool = True
                      ) -> Optional[Path]:
    if is_remote_src(src):
        logger.warning(f"Remote image URL ({src}); skipping embed.")
        return None

    candidates = image_path_candidates(src, foundry_data, scene_path)
    for c in candidates:
        if c.is_file():
            return c

    if warn_missing:
        logger.warning(f"Could not locate image file '{urllib.parse.unquote(src)}'.")
    return None


def scene_background_src(scene: Dict[str, Any]) -> Tuple[Optional[str], str]:
    """Return the primary Foundry background image source, if present."""
    levels = scene.get("levels")
    if isinstance(levels, list) and levels and isinstance(levels[0], dict):
        bg = levels[0].get("background") or {}
        if isinstance(bg, dict):
            src = bg.get("src")
            if src:
                return src, "levels[0].background.src"

    bg = scene.get("background") or {}
    if isinstance(bg, dict):
        src = bg.get("src")
        if src:
            return src, "background.src"

    src = scene.get("img")
    if src:
        return src, "img"
    return None, ""


def find_large_scene_tile(scene: Dict[str, Any], scene_w_px: float,
                          scene_h_px: float) -> Optional[Dict[str, Any]]:
    tiles = scene.get("tiles") or []
    if not isinstance(tiles, list):
        return None

    best_tile: Optional[Dict[str, Any]] = None
    best_score: Optional[Tuple[int, int, int, int, float, int]] = None
    for index, tile in enumerate(tiles):
        if not isinstance(tile, dict):
            continue
        texture = tile.get("texture") or {}
        if not isinstance(texture, dict):
            continue
        src = texture.get("src")
        if not isinstance(src, str) or not src or not is_image_src(src):
            continue

        width = as_float(tile.get("width"), 0.0) or 0.0
        height = as_float(tile.get("height"), 0.0) or 0.0
        if width <= 0 or height <= 0:
            continue

        if scene_w_px > 0 and scene_h_px > 0:
            covers_scene = width >= scene_w_px * 0.5 and height >= scene_h_px * 0.5
            if not covers_scene:
                continue
        else:
            covers_scene = True

        decoded_src = urllib.parse.unquote(src).lower()
        exact_size = int(
            scene_w_px > 0 and scene_h_px > 0
            and abs(width - scene_w_px) < 1.0
            and abs(height - scene_h_px) < 1.0
        )
        maps_path = int("/maps/" in decoded_src)
        visible = int(not tile.get("hidden"))
        area = width * height
        score = (int(covers_scene), exact_size, maps_path, visible, area, -index)
        if best_score is None or score > best_score:
            best_score = score
            best_tile = tile

    return best_tile


def resolve_image_path(scene: Dict[str, Any], foundry_data: Optional[Path],
                       scene_path: Path, explicit_image: Optional[Path],
                       scene_w_px: float, scene_h_px: float
                       ) -> Optional[ResolvedImage]:
    """Find the image and placement used as the UVTT map background."""
    tile = find_large_scene_tile(scene, scene_w_px, scene_h_px)

    if explicit_image is not None:
        img_path = resolve_image_src(str(explicit_image), foundry_data, scene_path)
        if img_path is None:
            return None
        if tile is not None:
            return ResolvedImage(
                path=img_path,
                source="--image with scene tile placement",
                target_w_px=as_float(tile.get("width"), scene_w_px),
                target_h_px=as_float(tile.get("height"), scene_h_px),
                origin_x_px=as_float(tile.get("x"), None),
                origin_y_px=as_float(tile.get("y"), None),
            )
        return ResolvedImage(path=img_path, source="--image")

    src, source = scene_background_src(scene)
    if src:
        img_path = resolve_image_src(src, foundry_data, scene_path)
        if img_path is not None:
            return ResolvedImage(path=img_path, source=source)
        if tile is not None:
            logger.warning("Background image unresolved; trying largest map tile.")

    if tile is not None:
        texture = tile.get("texture") or {}
        src = texture.get("src") if isinstance(texture, dict) else None
        if isinstance(src, str):
            img_path = resolve_image_src(src, foundry_data, scene_path)
            if img_path is not None:
                logger.warning(
                    "No background.src/img; using largest tile "
                    f"({urllib.parse.unquote(src)}).")
                return ResolvedImage(
                    path=img_path,
                    source="tiles[].texture.src",
                    target_w_px=as_float(tile.get("width"), scene_w_px),
                    target_h_px=as_float(tile.get("height"), scene_h_px),
                    origin_x_px=as_float(tile.get("x"), None),
                    origin_y_px=as_float(tile.get("y"), None),
                )

    thumb = scene.get("thumb")
    if isinstance(thumb, str) and thumb:
        logger.warning(
            f"Only a thumbnail found ({urllib.parse.unquote(thumb)}); no map "
            "image embedded. Pass --image PATH.")
    else:
        logger.warning(
            "No background image reference; no map embedded. Pass --image PATH.")
    return None


def read_jpeg_dimensions(img_path: Path) -> Optional[Tuple[int, int]]:
    with open(img_path, "rb") as f:
        if f.read(2) != b"\xff\xd8":
            return None

        while True:
            marker_start = f.read(1)
            if marker_start == b"":
                return None
            if marker_start != b"\xff":
                continue

            marker = f.read(1)
            while marker == b"\xff":
                marker = f.read(1)
            if marker == b"":
                return None

            marker_code = marker[0]
            if marker_code in (0xD8, 0xD9):
                continue

            raw_len = f.read(2)
            if len(raw_len) != 2:
                return None
            seg_len = struct.unpack(">H", raw_len)[0]
            if seg_len < 2:
                return None

            if marker_code in (
                0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
            ):
                data = f.read(5)
                if len(data) != 5:
                    return None
                height = struct.unpack(">H", data[1:3])[0]
                width = struct.unpack(">H", data[3:5])[0]
                return width, height

            f.seek(seg_len - 2, os.SEEK_CUR)


def read_webp_dimensions(header: bytes) -> Optional[Tuple[int, int]]:
    if len(header) < 30 or header[:4] != b"RIFF" or header[8:12] != b"WEBP":
        return None

    chunk = header[12:16]
    if chunk == b"VP8X" and len(header) >= 30:
        width = 1 + int.from_bytes(header[24:27], "little")
        height = 1 + int.from_bytes(header[27:30], "little")
        return width, height

    if chunk == b"VP8L" and len(header) >= 25:
        b0, b1, b2, b3 = header[21], header[22], header[23], header[24]
        width = 1 + (((b1 & 0x3F) << 8) | b0)
        height = 1 + (((b3 & 0x0F) << 10) | (b2 << 2) | ((b1 & 0xC0) >> 6))
        return width, height

    if chunk == b"VP8 " and len(header) >= 30 and header[23:26] == b"\x9d\x01\x2a":
        width = struct.unpack("<H", header[26:28])[0] & 0x3FFF
        height = struct.unpack("<H", header[28:30])[0] & 0x3FFF
        return width, height

    return None


def read_image_dimensions_without_pillow(img_path: Path) -> Optional[Tuple[int, int]]:
    with open(img_path, "rb") as f:
        header = f.read(64)

    if len(header) >= 24 and header.startswith(b"\x89PNG\r\n\x1a\n"):
        return struct.unpack(">II", header[16:24])

    if len(header) >= 10 and header[:6] in (b"GIF87a", b"GIF89a"):
        return struct.unpack("<HH", header[6:10])

    webp_dims = read_webp_dimensions(header)
    if webp_dims is not None:
        return webp_dims

    return read_jpeg_dimensions(img_path)


def encode_image(img_path: Path, max_size: int,
                 target_w_px: float, target_h_px: float
                 ) -> Tuple[Optional[str], int, int]:
    """Resize/encode the image; return (base64_png, final_w_px, final_h_px)."""
    if not HAVE_PIL:
        dims = read_image_dimensions_without_pillow(img_path)
        if dims is None:
            raise ImageEncodeError(
                "Pillow not installed and image dimensions unreadable; "
                "install Pillow.")

        source_w, source_h = dims
        if max(source_w, source_h) > max_size:
            raise ImageEncodeError(
                f"Pillow not installed and image {source_w}x{source_h} exceeds "
                f"{max_size}px limit; install Pillow to downscale.")

        target_w = max(1, int(round(target_w_px)))
        target_h = max(1, int(round(target_h_px)))
        if (source_w, source_h) != (target_w, target_h):
            logger.warning(
                "Pillow not installed; embedding bytes as-is without resize "
                "(walls may misalign).")
        else:
            logger.warning(
                "Pillow not installed; embedding bytes as-is (within "
                f"{max_size}px limit).")
        with open(img_path, "rb") as f:
            return base64.b64encode(f.read()).decode("ascii"), source_w, source_h

    with Image.open(img_path) as im:
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGBA")
        sw, sh = im.size
        logger.info(f"Image source size: {sw}x{sh}")

        # Step 1: resize to the Foundry scene dimensions so the image
        # corresponds to the same pixel range the wall coords use. Foundry
        # commonly stores a high-res asset and renders it scaled to the
        # scene -- our walls are in scene-pixel space, so the embedded
        # image must be too.
        target_w = max(1, int(round(target_w_px)))
        target_h = max(1, int(round(target_h_px)))
        if (sw, sh) != (target_w, target_h):
            logger.info(f"Resizing to scene dimensions {target_w}x{target_h}")
            im = im.resize((target_w, target_h), Image.LANCZOS)

        # Step 2: apply --max-image-size cap (output file size control).
        # The map_size stays the same -- pixels_per_grid scales instead.
        w, h = im.size
        long_edge = max(w, h)
        if long_edge > max_size:
            scale = max_size / float(long_edge)
            new_size = (max(1, int(round(w * scale))),
                        max(1, int(round(h * scale))))
            logger.info(
                f"Downscaling to {new_size[0]}x{new_size[1]} "
                f"(--max-image-size {max_size})")
            im = im.resize(new_size, Image.LANCZOS)

        buf = io.BytesIO()
        im.save(buf, format="PNG", optimize=True)
        data = buf.getvalue()
        logger.info(f"Encoded PNG size: {len(data) / (1024 * 1024):.2f} MB")
        return base64.b64encode(data).decode("ascii"), im.width, im.height


def foundry_wall_flags(w: Dict[str, Any]) -> Dict[str, Any]:
    """Return raw Foundry wall metadata for UVTT extension consumers."""
    door = wall_int(w, "door", 0)
    sight = wall_int(w, "sight", 20)
    move = wall_int(w, "move", 20)
    light = wall_int(w, "light", 20)
    sound = wall_int(w, "sound", 20)
    direction = wall_int(w, "dir", 0)
    door_state = wall_int(w, "ds", 0)
    threshold = w.get("threshold")

    sense: Dict[str, Any] = {
        "door": door,
        "door_name": door_name(door),
        "sight": sight,
        "sight_name": sense_name(sight),
        "move": move,
        "move_name": sense_name(move),
        "light": light,
        "light_name": sense_name(light),
        "sound": sound,
        "sound_name": sense_name(sound),
    }
    if threshold:
        sense["threshold"] = threshold

    return {
        "foundry_direction": direction,
        "foundry_direction_name": direction_name(direction),
        "foundry_door_state": door_state,
        "foundry_door_state_name": door_state_name(door_state),
        "foundry_sense": sense,
    }


def classify_wall(w: Dict[str, Any]) -> str:
    """Classify a wall: 'door', 'secret_door', 'window', 'wall', 'terrain',
    'invisible', or 'unrecognized'."""
    door = wall_int(w, "door", 0)
    sight = wall_int(w, "sight", 20)
    move = wall_int(w, "move", 20)
    light = wall_int(w, "light", 20)
    direction = wall_int(w, "dir", 0)

    threshold = w.get("threshold") or {}
    t_light = threshold.get("light")
    t_sight = threshold.get("sight")

    # Some Foundry content encodes window-like openings as secret doors with
    # proximity/threshold senses. Preserve those as open portals so they use
    # the window asset instead of the secret-door asset.
    is_window_like = (
        t_light is not None and t_sight is not None
        and light != move and sight != move
    )
    if door in (0, 2) and is_window_like:
        return "window"

    if door == 1:
        return "door"
    if door == 2:
        return "secret_door"
    if door != 0:
        return "unrecognized"

    # Directional Foundry walls cannot be faithfully represented by standard
    # UVTT line_of_sight, so keep them in extension metadata instead of
    # flattening them into two-way walls.
    if direction != 0:
        return "unrecognized"

    # Solid wall: full sight + full movement block.
    if sight == 20 and move == 20:
        return "wall"

    # Terrain wall: blocks movement (move=20), limited sight (sight=10),
    # no threshold pattern. These are usually furniture-like obstacles.
    if move == 20 and sight == 10:
        return "terrain"

    # Invisible wall: blocks movement but not sight.
    if move == 20 and sight == 0:
        return "invisible"

    return "unrecognized"


def convert_walls(scene: Dict[str, Any], grid_size: float,
                  pad_x_px: float, pad_y_px: float
                  ) -> Tuple[List[List[Dict[str, float]]],
                             List[Dict[str, Any]],
                             List[Dict[str, Any]],
                             List[Dict[str, Any]],
                             List[Dict[str, Any]],
                             Dict[str, Any]]:
    """Convert Foundry walls to UVTT geometry; return (line_of_sight, portals,
    terrain_walls, invisible_walls, unrecognized_walls, report)."""
    walls = scene.get("walls") or []
    line_of_sight: List[List[Dict[str, float]]] = []
    portals: List[Dict[str, Any]] = []
    terrain_walls: List[Dict[str, Any]] = []
    invisible_walls: List[Dict[str, Any]] = []
    unrecognized: List[Dict[str, Any]] = []

    counts = Counter()
    unrecognized_combos: Counter = Counter()
    terrain_combos: Counter = Counter()
    invisible_combos: Counter = Counter()

    def to_grid(px: float, py: float) -> Tuple[float, float]:
        return ((px - pad_x_px) / grid_size,
                (py - pad_y_px) / grid_size)

    for w in walls:
        if not isinstance(w, dict):
            counts["malformed"] += 1
            continue

        c = w.get("c")
        if not (isinstance(c, list) and len(c) == 4):
            counts["malformed"] += 1
            continue

        c0 = as_float(c[0])
        c1 = as_float(c[1])
        c2 = as_float(c[2])
        c3 = as_float(c[3])
        if c0 is None or c1 is None or c2 is None or c3 is None:
            counts["malformed"] += 1
            continue

        x1, y1 = to_grid(c0, c1)
        x2, y2 = to_grid(c2, c3)
        p1 = {"x": x1, "y": y1}
        p2 = {"x": x2, "y": y2}

        kind = classify_wall(w)
        counts[kind] += 1
        flags = foundry_wall_flags(w)

        if kind == "wall":
            line_of_sight.append([p1, p2])
        elif kind in ("door", "secret_door", "window"):
            portal = build_portal(p1, p2, closed=(kind != "window"))
            portal["flags"] = flags
            if kind == "secret_door":
                portal["secret"] = True
            if kind == "window":
                threshold = w.get("threshold")
                if threshold:
                    portal.setdefault("flags", {})["foundry_threshold"] = threshold
            portals.append(portal)
        elif kind == "terrain":
            combo = (
                wall_int(w, "sight", 20),
                wall_int(w, "move", 20),
                wall_int(w, "light", 20),
                wall_int(w, "sound", 20),
                wall_int(w, "dir", 0),
            )
            terrain_combos[combo] += 1
            terrain_walls.append({
                "points": [p1, p2],
                "sense": {
                    "door":  door_name(wall_int(w, "door", 0)),
                    "sight": sense_name(wall_int(w, "sight", 20)),
                    "move":  sense_name(wall_int(w, "move", 20)),
                    "light": sense_name(wall_int(w, "light", 20)),
                    "sound": sense_name(wall_int(w, "sound", 20)),
                },
                "flags": flags,
            })
        elif kind == "invisible":
            combo = (
                wall_int(w, "sight", 20),
                wall_int(w, "move", 20),
                wall_int(w, "light", 20),
                wall_int(w, "sound", 20),
                wall_int(w, "dir", 0),
            )
            invisible_combos[combo] += 1
            invisible_walls.append({
                "points": [p1, p2],
                "sense": {
                    "door":  door_name(wall_int(w, "door", 0)),
                    "sight": sense_name(wall_int(w, "sight", 20)),
                    "move":  sense_name(wall_int(w, "move", 20)),
                    "light": sense_name(wall_int(w, "light", 20)),
                    "sound": sense_name(wall_int(w, "sound", 20)),
                },
                "flags": flags,
            })
        else:  # unrecognized
            combo = (
                wall_int(w, "door", 0),
                wall_int(w, "sight", 20),
                wall_int(w, "move", 20),
                wall_int(w, "light", 20),
                wall_int(w, "sound", 20),
                wall_int(w, "dir", 0),
            )
            unrecognized_combos[combo] += 1
            unrecognized.append({
                "points": [p1, p2],
                "sense": {
                    "door":  door_name(wall_int(w, "door", 0)),
                    "sight": sense_name(wall_int(w, "sight", 20)),
                    "move":  sense_name(wall_int(w, "move", 20)),
                    "light": sense_name(wall_int(w, "light", 20)),
                    "sound": sense_name(wall_int(w, "sound", 20)),
                },
                "threshold": w.get("threshold"),
                "flags": flags,
            })

    report = {
        "counts": dict(counts),
        "terrain_combos": [
            {
                "count": n,
                "sight": sense_name(combo[0]),
                "move":  sense_name(combo[1]),
                "light": sense_name(combo[2]),
                "sound": sense_name(combo[3]),
                "direction": direction_name(combo[4]),
            }
            for combo, n in terrain_combos.most_common()
        ],
        "invisible_combos": [
            {
                "count": n,
                "sight": sense_name(combo[0]),
                "move":  sense_name(combo[1]),
                "light": sense_name(combo[2]),
                "sound": sense_name(combo[3]),
                "direction": direction_name(combo[4]),
            }
            for combo, n in invisible_combos.most_common()
        ],
        "unrecognized_combos": [
            {
                "count": n,
                "door":  door_name(combo[0]),
                "sight": sense_name(combo[1]),
                "move":  sense_name(combo[2]),
                "light": sense_name(combo[3]),
                "sound": sense_name(combo[4]),
                "direction": direction_name(combo[5]),
            }
            for combo, n in unrecognized_combos.most_common()
        ],
    }
    return line_of_sight, portals, terrain_walls, invisible_walls, unrecognized, report


def build_portal(p1: Dict[str, float], p2: Dict[str, float], closed: bool) -> Dict[str, Any]:
    dx = p2["x"] - p1["x"]
    dy = p2["y"] - p1["y"]
    return {
        "position": {"x": (p1["x"] + p2["x"]) / 2.0, "y": (p1["y"] + p2["y"]) / 2.0},
        "bounds": [p1, p2],
        "rotation": math.atan2(dy, dx),
        "closed": closed,
        "freestanding": False,
    }


def convert_lights(scene: Dict[str, Any], grid_size: float,
                   pad_x_px: float, pad_y_px: float) -> List[Dict[str, Any]]:
    lights_in = scene.get("lights") or []
    out: List[Dict[str, Any]] = []
    for light in lights_in:
        if not isinstance(light, dict):
            continue

        cfg = light.get("config") or {}
        if not isinstance(cfg, dict):
            cfg = {}

        color = cfg.get("color") or "#ffffff"
        if isinstance(color, str) and color.startswith("#"):
            color = color[1:]
        dim = as_float(cfg.get("dim"), 0.0) or 0.0
        bright = as_float(cfg.get("bright"), 0.0) or 0.0
        lx = as_float(light.get("x"), 0.0) or 0.0
        ly = as_float(light.get("y"), 0.0) or 0.0
        out.append({
            "position": {
                "x": (lx - pad_x_px) / grid_size,
                "y": (ly - pad_y_px) / grid_size,
            },
            "range": dim if dim > 0 else bright,
            "intensity": as_float(cfg.get("alpha"), 0.5) or 0.5,
            "color": color,
            "shadows": bool(cfg.get("walls", True)),
        })
    return out


def build_uvtt(scene: Dict[str, Any], image_b64: Optional[str],
               grid_size: float, map_w_px: float, map_h_px: float,
               image_w_px: int, image_h_px: int,
               line_of_sight: List[List[Dict[str, float]]],
               portals: List[Dict[str, Any]],
               lights: List[Dict[str, Any]],
               terrain_walls: List[Dict[str, Any]],
               invisible_walls: List[Dict[str, Any]],
               unrecognized_walls: List[Dict[str, Any]],
               include_secret: bool) -> Dict[str, Any]:
    cols = map_w_px / grid_size if grid_size else 0
    rows = map_h_px / grid_size if grid_size else 0

    # Walls are in grid-unit coords spanning [0, cols] x [0, rows]. The
    # embedded image must occupy exactly that range so DMHub renders walls
    # in alignment with the picture. After --max-image-size downsampling,
    # the image has fewer pixels than scene_w*scene_h, so we shrink
    # pixels_per_grid proportionally to keep the relationship
    # `image_w_px == cols * pixels_per_grid` true.
    if image_w_px > 0 and cols > 0:
        pixels_per_grid = image_w_px / cols
    else:
        pixels_per_grid = grid_size

    if not include_secret:
        for p in portals:
            p.pop("secret", None)

    uvtt: Dict[str, Any] = {
        "format": 0.3,
        "resolution": {
            "map_origin": {"x": 0, "y": 0},
            "map_size": {"x": cols, "y": rows},
            "pixels_per_grid": pixels_per_grid,
        },
        "line_of_sight": line_of_sight,
        "objects_line_of_sight": [],
        "portals": portals,
        "lights": lights,
        "environment": {
            "baked_lighting": False,
            "ambient_light": "ffffff",
        },
        "image": image_b64 or "",
    }
    if terrain_walls:
        uvtt["foundry_terrain_walls"] = terrain_walls
    if invisible_walls:
        uvtt["foundry_invisible_walls"] = invisible_walls
    if unrecognized_walls:
        uvtt["foundry_unrecognized_walls"] = unrecognized_walls

    name = scene.get("name")
    if name:
        uvtt.setdefault("foundry_scene", {})["name"] = name
    return uvtt


def print_report(report: Dict[str, Any], terrain_count: int,
                 invisible_count: int,
                 unrecognized_count: int) -> None:
    counts = report["counts"]
    n_walls = counts.get("wall", 0)
    n_doors = counts.get("door", 0)
    n_secret = counts.get("secret_door", 0)
    n_windows = counts.get("window", 0)
    n_malformed = counts.get("malformed", 0)

    print(f"Recognized: {n_walls} walls, {n_doors} doors, "
          f"{n_secret} secret doors, {n_windows} true windows")

    if n_malformed:
        print(f"Malformed walls skipped: {n_malformed}")

    terrain_combos = report.get("terrain_combos") or []
    if terrain_count > 0:
        print()
        print(f"Terrain walls (partial sight + full move-block, "
              f"furniture-like: {terrain_count} walls in "
              f"{len(terrain_combos)} combinations) -- emitted as "
              f"foundry_terrain_walls. DMHub can import them with the selected "
              f"terrain wall material:")
        for c in terrain_combos:
            print(f"  {c['count']:4d}x  sight={c['sight']:<9} "
                  f"move={c['move']:<9} light={c['light']:<9} "
                  f"sound={c['sound']:<9} direction={c['direction']}")

    invisible_combos = report.get("invisible_combos") or []
    if invisible_count > 0:
        print()
        print(f"Invisible walls (movement block + transparent sight: "
              f"{invisible_count} walls in {len(invisible_combos)} "
              f"combinations) -- emitted as foundry_invisible_walls. DMHub "
              f"can import them with the selected invisible wall material:")
        for c in invisible_combos:
            print(f"  {c['count']:4d}x  sight={c['sight']:<9} "
                  f"move={c['move']:<9} light={c['light']:<9} "
                  f"sound={c['sound']:<9} direction={c['direction']}")

    combos = report.get("unrecognized_combos") or []
    if unrecognized_count == 0:
        if terrain_count == 0 and invisible_count == 0:
            print("Unrecognized: 0")
        return

    print()
    print(f"Unrecognized ({unrecognized_count} walls in {len(combos)} "
          f"combinations) -- often GM-only navigation aids; set the "
          f"Unrecognized walls row to Line if you want them as plain walls:")
    for c in combos:
        print(f"  {c['count']:4d}x  door={c['door']:<11} "
              f"sight={c['sight']:<9} move={c['move']:<9} "
              f"light={c['light']:<9} sound={c['sound']:<9} "
              f"direction={c['direction']}")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Convert a Foundry VTT scene JSON to a UVTT (.dd2vtt) file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("scene_json", type=Path,
                   help="Path to the Foundry scene JSON export.")
    p.add_argument("--foundry-data", type=Path, default=None,
                   help="Path to the Foundry user data directory (for resolving "
                        "background.src).")
    p.add_argument("-o", "--output", type=Path, default=None,
                   help="Output .dd2vtt path (default: alongside input with "
                        ".dd2vtt extension).")
    p.add_argument("--image", type=Path, default=None,
                   help="Explicit map image path to embed. Useful when a "
                        "Foundry export stores the active map as a tile or "
                        "omits background.src.")
    p.add_argument("--no-embed-image", action="store_true",
                   help="Do not embed the background image (image: \"\").")
    p.add_argument("--max-image-size", type=int, default=DMHUB_MAX_IMAGE_SIZE,
                   help="Downscale the long edge of the image to at most N "
                        f"pixels before embedding (default: {DMHUB_MAX_IMAGE_SIZE}; "
                        f"hard max: {DMHUB_MAX_IMAGE_SIZE}).")
    p.add_argument("--no-secret-extension", action="store_true",
                   help="Drop the non-spec 'secret: true' field on secret-door "
                        "portals. Secret doors will fall back to normal doors "
                        "on import.")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    if not args.scene_json.is_file():
        logger.error(f"scene JSON not found: {args.scene_json}")
        return 2
    if args.max_image_size <= 0:
        logger.error("--max-image-size must be greater than 0")
        return 2
    if args.max_image_size > DMHUB_MAX_IMAGE_SIZE:
        logger.warning(
            f"--max-image-size {args.max_image_size} exceeds "
            f"{DMHUB_MAX_IMAGE_SIZE}px limit; clamping to {DMHUB_MAX_IMAGE_SIZE}.")
        args.max_image_size = DMHUB_MAX_IMAGE_SIZE

    scene = load_scene(args.scene_json)

    grid = scene.get("grid")
    if isinstance(grid, dict):
        grid_size = as_float(grid.get("size"), 100.0) or 100.0
    elif grid is not None:
        grid_size = as_float(grid, 100.0) or 100.0
    else:
        logger.warning("No grid info; defaulting to 100 px per grid.")
        grid_size = 100.0
    if grid_size <= 0:
        logger.warning("Invalid grid size; defaulting to 100 px per grid.")
        grid_size = 100.0

    # Foundry walls are stored in canvas-space coordinates which include
    # the scene's padding region and the user's optional shiftX/shiftY
    # background offset. The background image is rendered at canvas
    # position (padding*width + shiftX, padding*height + shiftY). To
    # produce image-relative pixel coords (what UVTT consumers expect),
    # we subtract both contributions from every wall/light coord before
    # dividing by grid size.
    #
    # Foundry V12+ adds a `levels[0].textures` object that may further
    # shift/scale the rendered background relative to the scene canvas:
    #
    #   levels[0].textures = {
    #       anchorX, anchorY,     -- (usually 0.5, 0.5)
    #       offsetX, offsetY,     -- pixel shift applied to the image
    #       fit,                  -- "fill" | "contain" | "cover" | ...
    #       scaleX, scaleY,       -- scale factors (1.0 = no change)
    #       rotation,             -- degrees (we don't support non-zero)
    #   }
    #
    # When offsetX/Y or scaleX/Y are non-default, walls drawn against the
    # canvas no longer line up with the rendered image. We undo those
    # transforms here so the embedded image (which we re-render to scene
    # size) aligns with the wall coords.
    #
    # Rotation != 0 is rare and complex; we log a warning but don't try
    # to handle it (the user would have to clear the rotation in Foundry
    # before exporting).
    padding = as_float(scene.get("padding"), 0.0) or 0.0
    shift_x = as_float(scene.get("shiftX"), 0.0) or 0.0
    shift_y = as_float(scene.get("shiftY"), 0.0) or 0.0
    scene_w_px = as_float(scene.get("width"), 0.0) or 0.0
    scene_h_px = as_float(scene.get("height"), 0.0) or 0.0

    first_level: Dict[str, Any] = {}
    levels = scene.get("levels")
    if isinstance(levels, list) and levels and isinstance(levels[0], dict):
        first_level = levels[0]
    textures = first_level.get("textures") or {}
    if not isinstance(textures, dict):
        textures = {}
    tex_offset_x = as_float(textures.get("offsetX"), 0.0) or 0.0
    tex_offset_y = as_float(textures.get("offsetY"), 0.0) or 0.0
    tex_scale_x = as_float(textures.get("scaleX"), 1.0) or 1.0
    tex_scale_y = as_float(textures.get("scaleY"), 1.0) or 1.0
    tex_rotation = as_float(textures.get("rotation"), 0.0) or 0.0
    tex_fit = textures.get("fit") or "fill"

    if abs(tex_rotation) > 0.01:
        logger.warning(
            f"textures.rotation = {tex_rotation} not undone; clear it in "
            "Foundry for accurate alignment.")
    if abs(tex_scale_x - 1.0) > 0.01 or abs(tex_scale_y - 1.0) > 0.01:
        logger.warning(
            f"textures.scaleX/Y = {tex_scale_x}, {tex_scale_y} (non-default); "
            "walls may misalign. Reset to 1 in Foundry.")
    if tex_fit and tex_fit != "fill":
        logger.warning(
            f"textures.fit = '{tex_fit}' (expected 'fill'); walls may misalign.")

    pad_x_px = padding * scene_w_px + shift_x + tex_offset_x
    pad_y_px = padding * scene_h_px + shift_y + tex_offset_y
    map_w_px = scene_w_px
    map_h_px = scene_h_px

    logger.info(f"Grid size: {grid_size} px per grid")
    logger.info(f"Scene size: {scene_w_px}x{scene_h_px} px")
    logger.info(f"Padding: {padding}; shiftX: {shift_x}; shiftY: {shift_y}")
    logger.info(
        f"textures.offsetX/Y: {tex_offset_x}, {tex_offset_y}; "
        f"fit={tex_fit}; scaleX/Y={tex_scale_x}, {tex_scale_y}")
    logger.info(f"Image-origin offset: ({pad_x_px}, {pad_y_px}) px")

    image_b64: Optional[str] = None
    image_w_px = 0
    image_h_px = 0
    if args.no_embed_image:
        src, _ = scene_background_src(scene)
        tile = None if src else find_large_scene_tile(scene, scene_w_px, scene_h_px)
        if tile is not None:
            tile_x = as_float(tile.get("x"), None)
            tile_y = as_float(tile.get("y"), None)
            tile_w = as_float(tile.get("width"), None)
            tile_h = as_float(tile.get("height"), None)
            if tile_x is not None:
                pad_x_px = tile_x
            if tile_y is not None:
                pad_y_px = tile_y
            if tile_w is not None:
                map_w_px = tile_w
            if tile_h is not None:
                map_h_px = tile_h
            logger.info(
                f"Using scene tile placement without embedding: "
                f"origin=({pad_x_px}, {pad_y_px}) px; "
                f"size={map_w_px}x{map_h_px} px")
    else:
        resolved_image = resolve_image_path(
            scene, args.foundry_data, args.scene_json, args.image,
            scene_w_px, scene_h_px)
        if resolved_image is not None:
            if resolved_image.origin_x_px is not None:
                pad_x_px = resolved_image.origin_x_px
            if resolved_image.origin_y_px is not None:
                pad_y_px = resolved_image.origin_y_px
            if resolved_image.target_w_px is not None:
                map_w_px = resolved_image.target_w_px
            if resolved_image.target_h_px is not None:
                map_h_px = resolved_image.target_h_px
            logger.info(f"Image source: {resolved_image.source}")
            logger.info(f"Image path: {resolved_image.path}")
            logger.info(f"Resolved image origin: ({pad_x_px}, {pad_y_px}) px")
            logger.info(f"Resolved map size: {map_w_px}x{map_h_px} px")
            try:
                image_b64, image_w_px, image_h_px = encode_image(
                    resolved_image.path, args.max_image_size,
                    map_w_px, map_h_px)
            except ImageEncodeError as e:
                logger.error(f"{e}")
                return 2

    line_of_sight, portals, terrain_walls, invisible_walls, unrecognized, report = convert_walls(
        scene, grid_size, pad_x_px, pad_y_px)
    lights = convert_lights(scene, grid_size, pad_x_px, pad_y_px)

    uvtt = build_uvtt(
        scene=scene,
        image_b64=image_b64,
        grid_size=grid_size,
        map_w_px=map_w_px,
        map_h_px=map_h_px,
        image_w_px=image_w_px,
        image_h_px=image_h_px,
        line_of_sight=line_of_sight,
        portals=portals,
        lights=lights,
        terrain_walls=terrain_walls,
        invisible_walls=invisible_walls,
        unrecognized_walls=unrecognized,
        include_secret=not args.no_secret_extension,
    )

    if image_w_px > 0:
        logger.info(
            f"Image final size: {image_w_px}x{image_h_px} px "
            f"-> pixels_per_grid="
            f"{uvtt['resolution']['pixels_per_grid']:.2f}")

    out_path = args.output or args.scene_json.with_suffix(".dd2vtt")
    payload = json.dumps(uvtt, separators=(",", ":"))
    out_path.write_text(payload, encoding="utf-8")

    size_mb = len(payload) / (1024 * 1024)
    print(f"Wrote {out_path} ({size_mb:.2f} MB)")
    if image_w_px > 0 and image_h_px > 0:
        print(f"Embedded image: {image_w_px}x{image_h_px}px "
              f"(max edge limit: {args.max_image_size}px)")
    if size_mb > 50:
        logger.warning(
            "Output exceeds 50 MB; DMHub may struggle. Try --max-image-size 2048.")

    print_report(report, len(terrain_walls), len(invisible_walls), len(unrecognized))
    return 0


if __name__ == "__main__":
    sys.exit(main())
