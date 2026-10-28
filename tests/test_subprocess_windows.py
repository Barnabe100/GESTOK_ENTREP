"""Tests de ``app.utils.subprocess_windows.no_console_window_kwargs`` (phase
amélioration UX, point 4).

Limite explicite, plus stricte que pour les autres composants « réservés à
Windows » de ce projet (ex. ``app.security.credential_vault``) : les
attributs utilisés par la branche Windows (``subprocess.STARTUPINFO``,
``subprocess.CREATE_NO_WINDOW``, ``subprocess.STARTF_USESHOWWINDOW``,
``subprocess.SW_HIDE``) n'existent **pas du tout** dans le module
``subprocess`` d'une installation Python non-Windows — ce n'est pas une
question de backend sélectionné à l'exécution (contrairement à
``keyring``), mais de code conditionnellement absent à l'import même du
module standard. Simuler ``sys.platform == "win32"`` ne les ferait donc
jamais apparaître : cette branche ne peut être exécutée que sur un poste
Windows réel (voir le rapport de ce lot pour la procédure de vérification
manuelle — absence de fenêtre CMD visible lors d'une sauvegarde/
restauration)."""
from __future__ import annotations

import sys

from app.utils.subprocess_windows import no_console_window_kwargs


def test_returns_no_extra_kwargs_on_the_current_non_windows_platform() -> None:
    assert sys.platform != "win32", "ce test suppose un sandbox non-Windows (voir la docstring de module)."
    assert no_console_window_kwargs() == {}


def test_is_safe_to_unpack_into_a_real_subprocess_call() -> None:
    """Preuve concrète (pas seulement « retourne un dict vide ») qu'aucun
    argument inattendu n'est introduit sur cette plateforme : un appel réel
    avec ``**no_console_window_kwargs()`` se comporte exactement comme sans
    lui."""
    import subprocess

    result = subprocess.run(
        [sys.executable, "-c", "print('ok')"], capture_output=True, text=True, check=False,
        **no_console_window_kwargs(),
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "ok"
