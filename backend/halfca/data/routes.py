"""Road geography from routes.json: cities, toll plazas, routes into Delhi."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from halfca import config


@dataclass(frozen=True)
class City:
    name: str
    state_code: str
    x: float
    y: float


@dataclass(frozen=True)
class RoutePlaza:
    id: str
    name: str
    frac: float
    km: float


@dataclass(frozen=True)
class Route:
    id: str
    name: str
    highway: str
    origin: str
    destination: str
    distance_km: float
    svg_path: str
    stops: dict[str, float]  # city -> km from origin
    plazas: tuple[RoutePlaza, ...]

    def plazas_after(self, km_from: float) -> tuple[RoutePlaza, ...]:
        """Plazas a truck crosses driving from km_from to the destination."""
        return tuple(p for p in self.plazas if p.km > km_from)


@dataclass(frozen=True)
class Leg:
    """A supplier city's road into Delhi: which route, and where on it the trip starts."""

    route: Route
    origin_city: str
    origin_km: float

    @property
    def distance_km(self) -> float:
        return round(self.route.distance_km - self.origin_km, 1)

    @property
    def plazas(self) -> tuple[RoutePlaza, ...]:
        return self.route.plazas_after(self.origin_km)


@dataclass(frozen=True)
class Geography:
    cities: dict[str, City]
    plaza_names: dict[str, str]
    routes: dict[str, Route]

    def leg_from(self, city: str) -> Leg | None:
        """The route a truck from `city` takes into Delhi (origin routes preferred)."""
        best: Leg | None = None
        for route in self.routes.values():
            if city in route.stops and city != route.destination:
                leg = Leg(route, city, route.stops[city])
                if best is None or leg.origin_km < best.origin_km:
                    best = leg
        return best


def _parse(raw: dict) -> Geography:
    cities = {c["name"]: City(c["name"], c["state_code"], c["x"], c["y"]) for c in raw["cities"]}
    plaza_names = {p["id"]: p["name"] for p in raw["plazas"]}
    routes = {}
    for r in raw["routes"]:
        routes[r["id"]] = Route(
            id=r["id"],
            name=r["name"],
            highway=r["highway"],
            origin=r["from"],
            destination=r["to"],
            distance_km=float(r["distance_km"]),
            svg_path=r["svg_path"],
            stops={s["city"]: float(s["km"]) for s in r["stops"]},
            plazas=tuple(
                RoutePlaza(p["id"], plaza_names[p["id"]], float(p["frac"]), float(p["km"]))
                for p in r["plazas"]
            ),
        )
    return Geography(cities, plaza_names, routes)


@lru_cache(maxsize=1)
def load(path: Path = config.ROUTES_PATH) -> Geography:
    return _parse(json.loads(path.read_text()))


def raw_json(path: Path = config.ROUTES_PATH) -> dict:
    return json.loads(path.read_text())
