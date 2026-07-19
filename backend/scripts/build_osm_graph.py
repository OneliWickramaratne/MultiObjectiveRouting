from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import networkx as nx
import requests


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.data_store import HOSPITALS  # noqa: E402


OVERPASS_URL = "https://overpass-api.de/api/interpreter"
DRIVABLE_HIGHWAYS = {
    "motorway",
    "motorway_link",
    "trunk",
    "trunk_link",
    "primary",
    "primary_link",
    "secondary",
    "secondary_link",
    "tertiary",
    "tertiary_link",
    "unclassified",
    "residential",
    "living_street",
    "service",
}
DEFAULT_SPEEDS = {
    "motorway": 70,
    "motorway_link": 45,
    "trunk": 60,
    "trunk_link": 40,
    "primary": 50,
    "primary_link": 35,
    "secondary": 40,
    "secondary_link": 30,
    "tertiary": 35,
    "tertiary_link": 25,
    "unclassified": 30,
    "residential": 25,
    "living_street": 15,
    "service": 15,
}
ROAD_RISK = {
    "motorway": 0.35,
    "motorway_link": 0.55,
    "trunk": 0.45,
    "trunk_link": 0.65,
    "primary": 0.75,
    "primary_link": 0.9,
    "secondary": 0.9,
    "secondary_link": 1.05,
    "tertiary": 1.0,
    "tertiary_link": 1.15,
    "unclassified": 1.1,
    "residential": 1.25,
    "living_street": 1.4,
    "service": 1.5,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the local Colombo OSM driving graph.")
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "data" / "osm" / "colombo_drive.graphml",
    )
    parser.add_argument("--margin", type=float, default=0.025)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    south = min(hospital.latitude for hospital in HOSPITALS) - args.margin
    north = max(hospital.latitude for hospital in HOSPITALS) + args.margin
    west = min(hospital.longitude for hospital in HOSPITALS) - args.margin
    east = max(hospital.longitude for hospital in HOSPITALS) + args.margin
    highway_filter = "|".join(sorted(DRIVABLE_HIGHWAYS))
    query = f"""
    [out:json][timeout:180];
    (
      way["highway"~"^({highway_filter})$"]({south},{west},{north},{east});
    );
    (._;>;);
    out body;
    """

    print(f"Downloading OSM roads for bbox {south:.5f},{west:.5f},{north:.5f},{east:.5f}")
    response = requests.post(
        OVERPASS_URL,
        data={"data": query},
        headers={"User-Agent": "ICU-Transfer-DSS/0.1 local-research-project"},
        timeout=240,
    )
    response.raise_for_status()
    elements = response.json()["elements"]

    node_elements = {
        str(element["id"]): element
        for element in elements
        if element.get("type") == "node"
    }
    graph = nx.DiGraph()
    for node_id, element in node_elements.items():
        tags = element.get("tags", {})
        graph.add_node(
            node_id,
            x=float(element["lon"]),
            y=float(element["lat"]),
            highway=str(tags.get("highway", "")),
        )

    for way in (element for element in elements if element.get("type") == "way"):
        tags = way.get("tags", {})
        highway = normalized_highway(tags.get("highway"))
        if highway not in DRIVABLE_HIGHWAYS:
            continue
        node_ids = [str(node_id) for node_id in way.get("nodes", [])]
        oneway = str(tags.get("oneway", "")).lower() in {"yes", "1", "true"} or str(
            tags.get("junction", "")
        ).lower() == "roundabout"
        reverse_only = str(tags.get("oneway", "")).lower() == "-1"
        if reverse_only:
            node_ids.reverse()
            oneway = True

        speed_kph = parse_speed(tags.get("maxspeed"), DEFAULT_SPEEDS[highway])
        for first, second in zip(node_ids, node_ids[1:]):
            if first not in graph or second not in graph:
                continue
            first_data = graph.nodes[first]
            second_data = graph.nodes[second]
            length = haversine_meters(
                float(first_data["y"]),
                float(first_data["x"]),
                float(second_data["y"]),
                float(second_data["x"]),
            )
            signal_penalty = 1.5 if second_data.get("highway") == "traffic_signals" else 0.0
            attributes = {
                "length": round(length, 3),
                "speed_kph": float(speed_kph),
                "risk": ROAD_RISK[highway] + signal_penalty,
                "highway": highway,
                "way_id": str(way["id"]),
                "name": str(tags.get("name", "")),
            }
            add_best_edge(graph, first, second, attributes)
            if not oneway:
                reverse_attributes = dict(attributes)
                reverse_attributes["risk"] = ROAD_RISK[highway] + (
                    1.5 if first_data.get("highway") == "traffic_signals" else 0.0
                )
                add_best_edge(graph, second, first, reverse_attributes)

    graph.remove_nodes_from(list(nx.isolates(graph)))
    largest_nodes = max(nx.weakly_connected_components(graph), key=len)
    graph = graph.subgraph(largest_nodes).copy()
    graph.graph.update(
        {
            "name": "Colombo ICU Transfer Driving Graph",
            "crs": "EPSG:4326",
            "source": "OpenStreetMap via Overpass API",
        }
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    nx.write_graphml(graph, args.output)
    print(f"Saved {len(graph.nodes):,} nodes and {len(graph.edges):,} edges to {args.output}")


def normalized_highway(value) -> str:
    if isinstance(value, list):
        return str(value[0])
    return str(value or "")


def parse_speed(value, fallback: float) -> float:
    if isinstance(value, list):
        value = value[0]
    text = str(value or "").lower()
    digits = "".join(character for character in text if character.isdigit() or character == ".")
    if not digits:
        return fallback
    speed = float(digits)
    if "mph" in text:
        speed *= 1.60934
    return min(max(speed, 5), 90)


def add_best_edge(graph: nx.DiGraph, first: str, second: str, attributes: dict) -> None:
    existing = graph.get_edge_data(first, second)
    if existing is None or float(attributes["length"]) < float(existing.get("length", math.inf)):
        graph.add_edge(first, second, **attributes)


def haversine_meters(
    latitude_1: float,
    longitude_1: float,
    latitude_2: float,
    longitude_2: float,
) -> float:
    radius = 6_371_000
    phi_1 = math.radians(latitude_1)
    phi_2 = math.radians(latitude_2)
    delta_phi = math.radians(latitude_2 - latitude_1)
    delta_lambda = math.radians(longitude_2 - longitude_1)
    value = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi_1) * math.cos(phi_2) * math.sin(delta_lambda / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


if __name__ == "__main__":
    main()
