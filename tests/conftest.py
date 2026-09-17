import base64
import json
import os

# Doit être défini avant tout import de PySide6 (y compris via le plugin pytest-qt).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import date
from pathlib import Path
from typing import Callable, Iterator

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.config.settings import Settings, get_settings
from app.db import session as db_session_module
from app.db.init_db import init_database
from app.db.seed import seed_reference_data
from app.models.enums import EditionLicence, StatutLicence
from app.models.license import Licence
from app.models.rbac import Role
from app.models.user import User
from app.security.password_hashing import hash_password
from app.services.auth.current_user import CurrentUser
from app.services.licensing.license_payload import KNOWN_FEATURES, LICENSE_FORMAT_VERSION, PRODUCT_NAME, canonical_json_bytes
from app.services.registry import ServiceRegistry, build_service_registry

DEFAULT_TEST_PASSWORD = "MotDePasse!23"

# Paire de clés Ed25519 éphémère, régénérée à chaque exécution de la suite de
# tests : sert UNIQUEMENT à signer la licence de test à accès complet
# provisionnée ci-dessous (voir _full_access_test_licence). Jamais persistée
# sur disque, jamais commitée, et sans aucun rapport avec la clé de
# production (app/services/licensing/public_key.py) — voir §17 du cahier des
# charges de la phase Licences : aucune clé privée ne doit exister dans les
# tests distribués. La clé privée de test ci-dessous n'est distribuée nulle
# part : elle n'existe qu'en mémoire, le temps du processus pytest.
_TEST_LICENSE_PRIVATE_KEY = Ed25519PrivateKey.generate()
TEST_LICENSE_PUBLIC_KEY_BYTES = _TEST_LICENSE_PRIVATE_KEY.public_key().public_bytes(
    encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw,
)


def _full_access_test_licence() -> Licence:
    """Licence à accès complet (toutes fonctionnalités connues, limites très
    larges, sans expiration), signée avec la clé de test éphémère ci-dessus.
    Provisionnée par défaut dans chaque base de test pour que les ~767 tests
    existants (aucun ne portant sur la licence) continuent de fonctionner
    une fois le contrôle de licence actif ; les tests dédiés à la licence
    remplacent ou omettent volontairement cette licence pour exercer les
    cas de blocage."""
    payload_dict = {
        "license_version": LICENSE_FORMAT_VERSION,
        "license_id": "TEST-FULL-ACCESS",
        "product": PRODUCT_NAME,
        "client": "Tests automatisés",
        "edition": EditionLicence.ENTREPRISE.value,
        "issued_at": date.today().isoformat(),
        "expires_at": None,
        "max_users": 9999,
        "max_devices": 9999,
        "features": sorted(KNOWN_FEATURES),
    }
    signature = _TEST_LICENSE_PRIVATE_KEY.sign(canonical_json_bytes(payload_dict))
    return Licence(
        client=payload_dict["client"], produit=payload_dict["product"], edition=EditionLicence.ENTREPRISE,
        date_emission=date.today(), date_expiration=None, max_users=9999, max_postes=9999,
        statut=StatutLicence.ACTIVE, payload_json=json.dumps(payload_dict),
        signature=base64.b64encode(signature).decode("ascii"),
    )


@pytest.fixture()
def test_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Settings]:
    """Configuration isolée pointant vers une base SQLite temporaire par test."""
    db_path = tmp_path / "test_stockmanager.db"
    monkeypatch.setenv("STOCKMANAGER_ENV", "test")
    monkeypatch.setenv("STOCKMANAGER_DB_PATH", str(db_path))
    monkeypatch.setenv("STOCKMANAGER_LOG_LEVEL", "DEBUG")

    get_settings.cache_clear()
    db_session_module.reset_engine_cache()

    yield get_settings()

    db_session_module.reset_engine_cache()
    get_settings.cache_clear()


@pytest.fixture()
def initialized_db(test_settings: Settings) -> Settings:
    """Base de test migrée (Alembic), pré-remplie avec les données de
    référence et une licence de test à accès complet (voir
    _full_access_test_licence) — les tests dédiés à la licence peuvent
    activer une licence différente par-dessus (la plus récente fait foi,
    voir LicenceRepository.get_current)."""
    init_database(test_settings)
    with db_session_module.session_scope(test_settings) as session:
        seed_reference_data(session)
        session.add(_full_access_test_licence())
    return test_settings


@pytest.fixture()
def make_user(initialized_db: Settings) -> Callable[..., None]:
    """Factory de test : crée un utilisateur avec le rôle donné."""

    def _make_user(
        role_name: str, username: str, password: str = DEFAULT_TEST_PASSWORD, actif: bool = True
    ) -> None:
        with db_session_module.session_scope(initialized_db) as session:
            role = session.query(Role).filter_by(nom=role_name).one()
            session.add(
                User(
                    username=username,
                    password_hash=hash_password(password),
                    role_id=role.id,
                    actif=actif,
                )
            )

    return _make_user


@pytest.fixture()
def make_stack(initialized_db: Settings) -> Callable[[], ServiceRegistry]:
    """Construit une pile de services neuve, non connectée (même registre que
    l'application), vérifiant les licences avec la clé publique de test
    (jamais la clé de production) — voir TEST_LICENSE_PUBLIC_KEY_BYTES."""

    def _make_stack() -> ServiceRegistry:
        return build_service_registry(initialized_db, license_public_key_bytes=TEST_LICENSE_PUBLIC_KEY_BYTES)

    return _make_stack


@pytest.fixture()
def login_as(
    make_user: Callable[..., None],
    make_stack: Callable[[], ServiceRegistry],
) -> Callable[..., tuple[ServiceRegistry, CurrentUser]]:
    """Crée un utilisateur avec le rôle donné, le connecte, et retourne (stack, current_user)."""

    counter = {"n": 0}

    def _login_as(role_name: str, password: str = DEFAULT_TEST_PASSWORD) -> tuple[ServiceRegistry, CurrentUser]:
        counter["n"] += 1
        username = f"test_{role_name.lower().replace(' ', '_')}_{counter['n']}"
        make_user(role_name, username, password)
        stack = make_stack()
        current_user = stack.auth.login(username, password)
        return stack, current_user

    return _login_as


@pytest.fixture()
def license_envelope_factory() -> Callable[..., str]:
    """Construit le texte JSON d'une enveloppe de licence signée (§3-4),
    pour les tests dédiés à la phase Licences. Signe par défaut avec la clé
    de test éphémère (donc vérifiable via TEST_LICENSE_PUBLIC_KEY_BYTES,
    utilisée par ``make_stack``/``login_as``) ; passer ``private_key`` pour
    simuler une signature avec une autre clé (scénario « mauvaise clé
    publique »), ou ``signature_override``/``payload_override`` pour simuler
    une falsification (§16)."""

    def _make(
        *,
        license_version: int = LICENSE_FORMAT_VERSION,
        license_id: str = "STK-TEST-0001",
        product: str = PRODUCT_NAME,
        client: str = "Client de test",
        edition: str = "STANDARD",
        issued_at: str | None = None,
        expires_at: str | None = None,
        max_users: int = 5,
        max_devices: int = 2,
        features: list[str] | None = None,
        private_key: Ed25519PrivateKey | None = None,
        signature_override: str | None = None,
        payload_override: dict | None = None,
    ) -> str:
        payload_dict = {
            "license_version": license_version,
            "license_id": license_id,
            "product": product,
            "client": client,
            "edition": edition,
            "issued_at": issued_at or date.today().isoformat(),
            "expires_at": expires_at,
            "max_users": max_users,
            "max_devices": max_devices,
            "features": features if features is not None else sorted(KNOWN_FEATURES),
        }
        signing_key = private_key or _TEST_LICENSE_PRIVATE_KEY
        signature = signing_key.sign(canonical_json_bytes(payload_dict))
        signature_b64 = signature_override if signature_override is not None else base64.b64encode(signature).decode("ascii")

        # payload_override permet de modifier la charge utile APRÈS signature
        # (falsification) — la signature reste calculée sur la version non
        # modifiée, exactement le scénario que la vérification doit détecter.
        final_payload = payload_override if payload_override is not None else payload_dict
        return json.dumps({"payload": final_payload, "signature": signature_b64})

    return _make
