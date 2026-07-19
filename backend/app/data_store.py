from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IcuWardCapacity:
    """Bed capacity for one ICU specialty ward within a hospital."""

    icu_type: str
    total_beds: int
    occupied_beds: int

    @property
    def available_beds(self) -> int:
        return max(self.total_beds - self.occupied_beds, 0)


@dataclass(frozen=True)
class Hospital:
    id: str
    name: str
    latitude: float
    longitude: float
    # A hospital can run more than one ICU specialty ward at once (e.g. a
    # tertiary hospital with both a Trauma ICU and a Cardiac ICU) — each
    # entry here is one ward with its own bed count.
    icu_capacity: tuple[IcuWardCapacity, ...]
    supports_trauma: bool = False
    supports_cardiac: bool = False
    supports_neuro: bool = False
    supports_pediatric: bool = False
    supports_maternity: bool = False
    has_ventilator_support: bool = True
    aliases: tuple[str, ...] = ()
    risk_modifier: float = 0.0

    @property
    def icu_types(self) -> tuple[str, ...]:
        return tuple(ward.icu_type for ward in self.icu_capacity)

    @property
    def total_beds(self) -> int:
        return sum(ward.total_beds for ward in self.icu_capacity)

    @property
    def occupied_beds(self) -> int:
        return sum(ward.occupied_beds for ward in self.icu_capacity)

    @property
    def available_beds(self) -> int:
        return max(self.total_beds - self.occupied_beds, 0)

    def available_beds_for(self, icu_type: str) -> int:
        """Available beds of a specific ICU type only — a hospital with a busy
        Cardiac ICU but a free Trauma ICU should not look "full" to a trauma
        request just because its overall total is low."""
        return sum(ward.available_beds for ward in self.icu_capacity if ward.icu_type == icu_type)

    def total_beds_for(self, icu_type: str) -> int:
        return sum(ward.total_beds for ward in self.icu_capacity if ward.icu_type == icu_type)


HOSPITALS: list[Hospital] = [
    Hospital(
        id="1",
        name="National Hospital Sri Lanka",
        latitude=6.918611,
        longitude=79.868889,
        icu_capacity=(
            IcuWardCapacity("Trauma ICU", total_beds=10, occupied_beds=8),
            IcuWardCapacity("General ICU", total_beds=6, occupied_beds=6),
            IcuWardCapacity("Cardiac ICU", total_beds=4, occupied_beds=4),
        ),
        supports_trauma=True,
        supports_cardiac=True,
        supports_neuro=True,
        aliases=("nhsl", "national_hospital"),
        risk_modifier=0.12,
    ),
    Hospital(
        id="2",
        name="Colombo South Teaching Hospital",
        latitude=6.86763,
        longitude=79.87627,
        icu_capacity=(
            IcuWardCapacity("Cardiac ICU", total_beds=9, occupied_beds=7),
            IcuWardCapacity("General ICU", total_beds=6, occupied_beds=4),
        ),
        supports_trauma=True,
        supports_cardiac=True,
        aliases=("csth", "colombo_south"),
        risk_modifier=0.11,
    ),
    Hospital(
        id="3",
        name="Lady Ridgeway Hospital",
        latitude=6.91741,
        longitude=79.87631,
        icu_capacity=(
            IcuWardCapacity("Pediatric ICU", total_beds=12, occupied_beds=9),
        ),
        supports_pediatric=True,
        aliases=("lrh", "lady_ridgeway"),
        risk_modifier=0.08,
    ),
    Hospital(
        id="4",
        name="Sri Jayewardenepura General Hospital",
        latitude=6.8684233,
        longitude=79.9252167,
        icu_capacity=(
            IcuWardCapacity("Neuro ICU", total_beds=10, occupied_beds=7),
            IcuWardCapacity("General ICU", total_beds=8, occupied_beds=6),
        ),
        supports_trauma=True,
        supports_cardiac=True,
        supports_neuro=True,
        aliases=("sjgh", "sri_jayewardenepura"),
        risk_modifier=0.09,
    ),
    Hospital(
        id="5",
        name="De Soysa Hospital for Women",
        latitude=6.9198716,
        longitude=79.8702835,
        icu_capacity=(
            IcuWardCapacity("Maternity ICU", total_beds=10, occupied_beds=7),
        ),
        supports_maternity=True,
        aliases=("de_soysa", "dshw"),
        risk_modifier=0.08,
    ),
    Hospital(
        id="6",
        name="Nawaloka Hospital",
        latitude=6.9207,
        longitude=79.8534,
        icu_capacity=(
            IcuWardCapacity("General ICU", total_beds=9, occupied_beds=6),
            IcuWardCapacity("Cardiac ICU", total_beds=5, occupied_beds=4),
        ),
        supports_trauma=True,
        supports_cardiac=True,
        aliases=("nawaloka",),
        risk_modifier=0.10,
    ),
    Hospital(
        id="7",
        name="Asiri Central Hospital",
        latitude=6.920418,
        longitude=79.865584,
        icu_capacity=(
            IcuWardCapacity("Cardiac ICU", total_beds=10, occupied_beds=8),
            IcuWardCapacity("General ICU", total_beds=6, occupied_beds=4),
        ),
        supports_trauma=True,
        supports_cardiac=True,
        supports_neuro=True,
        aliases=("asiri", "asiri_central"),
        risk_modifier=0.07,
    ),
    Hospital(
        id="8",
        name="Lanka Hospital",
        latitude=6.8870,
        longitude=79.8720,
        icu_capacity=(
            IcuWardCapacity("Surgical ICU", total_beds=11, occupied_beds=8),
            IcuWardCapacity("General ICU", total_beds=6, occupied_beds=4),
        ),
        supports_trauma=True,
        supports_cardiac=True,
        supports_neuro=True,
        aliases=("lanka", "lanka_hospital"),
        risk_modifier=0.08,
    ),
    Hospital(
        id="9",
        name="Durdans Hospital",
        latitude=6.901925,
        longitude=79.853461,
        icu_capacity=(
            IcuWardCapacity("General ICU", total_beds=8, occupied_beds=5),
            IcuWardCapacity("Trauma ICU", total_beds=5, occupied_beds=4),
        ),
        supports_trauma=True,
        supports_cardiac=True,
        aliases=("durdans",),
        risk_modifier=0.10,
    ),
]


def get_hospital(hospital_id: str) -> Hospital | None:
    normalized = hospital_id.strip().lower()
    return next(
        (
            hospital
            for hospital in HOSPITALS
            if hospital.id == normalized
            or normalized in hospital.aliases
            or hospital.name.lower() == normalized
        ),
        None,
    )


def normalize_icu_type(icu_type: str) -> str:
    value = icu_type.strip().lower().replace("_", " ")
    aliases = {
        "medical": "General ICU",
        "surgical": "Surgical ICU",
        "surgical icu": "Surgical ICU",
        "trauma": "Trauma ICU",
        "trauma icu": "Trauma ICU",
        "cardiac": "Cardiac ICU",
        "cardiac icu": "Cardiac ICU",
        "neuro": "Neuro ICU",
        "neuro icu": "Neuro ICU",
        "general": "General ICU",
        "general icu": "General ICU",
        "pediatric": "Pediatric ICU",
        "pediatric icu": "Pediatric ICU",
        "maternity": "Maternity ICU",
        "maternity icu": "Maternity ICU",
    }
    return aliases.get(value, icu_type)


def hospital_supports_condition(hospital: Hospital, condition_type: str) -> bool:
    condition = condition_type.strip().lower()
    if condition in {"respiratory", "surgical", "sepsis", "general"}:
        # These are general adult critical-care presentations that any
        # non-specialty-restricted ICU can manage — trauma, cardiac, neuro,
        # surgical, or general — just not a pediatric- or maternity-only unit.
        return not ({"Pediatric ICU", "Maternity ICU"} & set(hospital.icu_types))
    if condition == "trauma":
        return hospital.supports_trauma
    if condition == "cardiac":
        return hospital.supports_cardiac
    if condition == "neuro":
        return hospital.supports_neuro
    if condition == "pediatric":
        return hospital.supports_pediatric
    if condition == "maternity":
        return hospital.supports_maternity
    return True
