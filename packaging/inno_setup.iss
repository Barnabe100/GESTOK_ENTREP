; Script Inno Setup pour StockManager Desktop (§4 du cahier des charges de
; la phase Packaging).
;
; Ne s'exécute que sur Windows, avec Inno Setup (https://jrsoftware.org/isinfo.php)
; installé — non disponible dans cet environnement de développement (Linux) :
; ce script n'a donc PAS été compilé ni testé ici (voir packaging/README.md,
; section "Non testé - nécessite Windows"). Il est prêt à être compilé une
; fois le build PyInstaller onedir produit sous dist/StockManager/.
;
; MyAppVersion doit rester synchronisé avec app/version.py (Inno Setup ne
; peut pas exécuter Python pour le lire directement) : voir
; packaging/generate_version_info.py, qui documente la même contrainte pour
; les métadonnées de l'exécutable.
#define MyAppName "StockManager Desktop"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "StockManager"
#define MyAppExeName "StockManager.exe"

[Setup]
AppId={{B6E2B6B0-6C0A-4A3B-9B0E-9E6B6F1C7A10}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
; Installation par utilisateur (pas de droits administrateur requis, §4) :
; installe sous %LOCALAPPDATA%\Programs\StockManager par défaut, jamais
; sous Program Files (qui exigerait une élévation). Les données utilisateur
; (base SQLite, licence, logs, sauvegardes) vivent de toute façon ailleurs
; (%APPDATA%\StockManager, voir app/config/settings.py) — totalement
; indépendantes de ce choix.
DefaultDirName={autopf}\StockManager
PrivilegesRequired=lowest
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=StockManager-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=app_icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "Créer un raccourci sur le Bureau"; GroupDescription: "Raccourcis supplémentaires :"; Flags: unchecked

[Files]
; Copie intégrale du dossier onedir produit par PyInstaller
; (dist/StockManager/) — jamais un fichier individuel choisi à la main, pour
; ne rien oublier des dépendances collectées par l'analyse PyInstaller.
Source: "..\dist\StockManager\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Désinstaller {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Lancer {#MyAppName}"; Flags: nowait postinstall skipifsilent

; Désinstallation propre (§4) : Inno Setup supprime par défaut uniquement ce
; qu'il a installé (le contenu de {app}) — jamais les données utilisateur
; (%APPDATA%\StockManager : base SQLite, licence, sauvegardes, logs), qui
; doivent survivre à une désinstallation comme à une mise à jour (§5/§7).
; Aucune section [UninstallDelete] ne cible donc ce dossier, volontairement.
