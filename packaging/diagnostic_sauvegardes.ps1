<#
    diagnostic_sauvegardes.ps1
    ==========================

    Script de diagnostic en LECTURE SEULE pour le système de sauvegarde de
    StockManager Desktop (mission « Diagnostic et résolution des pannes de
    sauvegarde », Axe 4).

    Objectif : collecter, sur le poste Windows réellement concerné, les
    informations nécessaires pour établir pourquoi (A) une sauvegarde
    manuelle apparaît "Invalide" sans message d'erreur visible, et/ou (B) la
    tâche planifiée Windows ne déclenche aucune sauvegarde — sans qu'il soit
    nécessaire de reproduire l'incident depuis l'environnement de
    développement (Linux), qui ne permet pas d'observer ces deux problèmes.

    GARANTIES :
    - Aucune opération destructive : ce script ne crée, ne modifie, ne
      supprime et ne déplace AUCUN fichier, AUCUNE tâche planifiée, AUCUN
      paramètre Windows. Il ne fait que lire et afficher.
    - Aucun secret collecté : ni mot de passe, ni clé de chiffrement, ni
      contenu d'archive. Seuls des noms de fichiers, chemins, tailles,
      dates, codes de retour et extraits de journaux (horodatage + niveau +
      message, jamais une valeur sensible) sont affichés.
    - Peut être relancé autant de fois que nécessaire sans aucun risque.

    UTILISATION :
        powershell -ExecutionPolicy Bypass -File diagnostic_sauvegardes.ps1

    Le résultat s'affiche à l'écran ET est enregistré dans un fichier texte
    horodaté du dossier courant (ex. "diagnostic_sauvegardes_20261126_193000.txt"),
    pour être transmis facilement.
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Continue"

$TranscriptPath = Join-Path -Path (Get-Location) -ChildPath ("diagnostic_sauvegardes_{0}.txt" -f (Get-Date -Format "yyyyMMdd_HHmmss"))
Start-Transcript -Path $TranscriptPath -NoClobber | Out-Null

function Write-Section {
    param([string]$Title)
    Write-Host ""
    Write-Host "==================================================================" -ForegroundColor Cyan
    Write-Host $Title -ForegroundColor Cyan
    Write-Host "==================================================================" -ForegroundColor Cyan
}

function Write-KeyValue {
    param([string]$Key, [object]$Value)
    if ($null -eq $Value -or $Value -eq "") { $Value = "(aucune valeur)" }
    Write-Host ("  {0,-38} : {1}" -f $Key, $Value)
}

$TaskName = "StockManager - Sauvegarde automatique"
$TaskNameOnLogon = "StockManager - Sauvegarde (ouverture de session)"

# ----------------------------------------------------------------------------
Write-Section "1. Système"
# ----------------------------------------------------------------------------
$os = Get-CimInstance -ClassName Win32_OperatingSystem -ErrorAction SilentlyContinue
Write-KeyValue "Nom du système" $os.Caption
Write-KeyValue "Version" $os.Version
Write-KeyValue "Architecture" $os.OSArchitecture
Write-KeyValue "Compte courant (whoami)" (whoami)
Write-KeyValue "USERDOMAIN" $env:USERDOMAIN
Write-KeyValue "USERNAME" $env:USERNAME
Write-KeyValue "APPDATA" $env:APPDATA

# ----------------------------------------------------------------------------
Write-Section "2. Installation StockManager"
# ----------------------------------------------------------------------------
$DataDir = Join-Path $env:APPDATA "StockManager"
Write-KeyValue "Dossier de données attendu" $DataDir
if (Test-Path $DataDir) {
    Write-KeyValue "Dossier de données existe" "Oui"
    Get-ChildItem -Path $DataDir -ErrorAction SilentlyContinue | ForEach-Object {
        Write-Host ("    - {0} ({1})" -f $_.Name, $(if ($_.PSIsContainer) { "dossier" } else { "{0} octets" -f $_.Length }))
    }
} else {
    Write-KeyValue "Dossier de données existe" "NON — vérifier si StockManager a bien été lancé au moins une fois sous ce compte."
}

# Recherche de l'exécutable réellement installé, sans supposer un seul
# emplacement : utile pour comparer au chemin réellement enregistré dans la
# tâche planifiée (section 5 ci-dessous).
Write-Host ""
Write-Host "  Recherche de StockManager.exe (peut prendre quelques secondes)..."
$CandidateDirs = @(
    "$env:ProgramFiles\StockManager",
    "${env:ProgramFiles(x86)}\StockManager",
    "$env:LOCALAPPDATA\Programs\StockManager"
) | Where-Object { $_ -and (Test-Path $_) }
foreach ($dir in $CandidateDirs) {
    Get-ChildItem -Path $dir -Filter "StockManager.exe" -Recurse -ErrorAction SilentlyContinue | ForEach-Object {
        Write-KeyValue "StockManager.exe trouvé" $_.FullName
        Write-KeyValue "  Le chemin contient un espace" ($_.FullName -match " ")
    }
}

# ----------------------------------------------------------------------------
Write-Section "3. Client PostgreSQL (pg_dump / pg_restore)"
# ----------------------------------------------------------------------------
foreach ($tool in @("pg_dump", "pg_restore")) {
    Write-Host ""
    Write-Host ("  -- {0} --" -f $tool)
    $onPath = Get-Command $tool -ErrorAction SilentlyContinue
    if ($onPath) {
        Write-KeyValue "Résolu via PATH" $onPath.Source
    } else {
        Write-KeyValue "Résolu via PATH" "NON"
    }

    # Mêmes emplacements standards que ``_windows_pg_bin_candidates`` côté
    # application (app/services/backups/postgresql_backup_engine.py) — pour
    # vérifier que ce script observe exactement ce que StockManager observe.
    $BaseDirs = @("C:\Program Files\PostgreSQL", "C:\Program Files (x86)\PostgreSQL")
    foreach ($base in $BaseDirs) {
        if (Test-Path $base) {
            Get-ChildItem -Path $base -Directory -ErrorAction SilentlyContinue | Sort-Object Name -Descending | ForEach-Object {
                $exePath = Join-Path $_.FullName "bin\$tool.exe"
                if (Test-Path $exePath) {
                    Write-KeyValue ("Trouvé sous {0}" -f $base) $exePath
                    try {
                        $version = & $exePath --version 2>&1
                        Write-KeyValue "  Version rapportée" ($version -join " ")
                    } catch {
                        Write-KeyValue "  Version rapportée" "Impossible d'exécuter --version : $($_.Exception.Message)"
                    }
                }
            }
        }
    }
}

# ----------------------------------------------------------------------------
Write-Section "4. Serveur PostgreSQL local (si présent sur ce poste)"
# ----------------------------------------------------------------------------
$pgServices = Get-Service -ErrorAction SilentlyContinue | Where-Object { $_.Name -like "postgresql*" }
if ($pgServices) {
    $pgServices | ForEach-Object { Write-KeyValue $_.Name $_.Status }
} else {
    Write-KeyValue "Service(s) PostgreSQL local" "Aucun trouvé (normal si le serveur est distant)."
}

# ----------------------------------------------------------------------------
Write-Section "5. Tâche(s) planifiée(s) StockManager"
# ----------------------------------------------------------------------------
foreach ($name in @($TaskName, $TaskNameOnLogon)) {
    Write-Host ""
    Write-Host ("  -- Tâche : {0} --" -f $name)
    $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if (-not $task) {
        Write-KeyValue "Existe" "NON"
        continue
    }
    Write-KeyValue "Existe" "Oui"
    Write-KeyValue "État (Enabled/Disabled/...)" $task.State
    Write-KeyValue "Principal (compte)" $task.Principal.UserId
    Write-KeyValue "Type de jeton (LogonType)" $task.Principal.LogonType
    Write-KeyValue "Niveau d'exécution" $task.Principal.RunLevel

    $action = $task.Actions | Select-Object -First 1
    if ($action) {
        Write-KeyValue "Commande (Execute)" $action.Execute
        Write-KeyValue "  Entourée de guillemets" ($action.Execute -match '^".*"$')
        Write-KeyValue "  Le chemin existe réellement" (Test-Path ($action.Execute.Trim('"')))
        Write-KeyValue "Arguments" $action.Arguments
        Write-KeyValue "Répertoire de travail (WorkingDirectory)" $action.WorkingDirectory
    }

    foreach ($trigger in $task.Triggers) {
        Write-Host ("    Déclencheur : {0}" -f $trigger.CimClass.CimClassName)
        Write-KeyValue "      Activé" $trigger.Enabled
        if ($trigger.StartBoundary) { Write-KeyValue "      Heure de départ" $trigger.StartBoundary }
    }

    $info = Get-ScheduledTaskInfo -TaskName $name -ErrorAction SilentlyContinue
    if ($info) {
        Write-KeyValue "Dernière exécution" $info.LastRunTime
        Write-KeyValue "Dernier résultat (code)" $info.LastTaskResult
        Write-KeyValue "  Interprétation" $(
            switch ($info.LastTaskResult) {
                0          { "Succès (0x0)" }
                267009     { "En cours d'exécution (0x41301)" }
                267011     { "N'a encore jamais été exécutée (0x41303)" }
                2147942402 { "Fichier introuvable (0x80070002) — chemin de la commande probablement invalide" }
                default    { "Voir https://learn.microsoft.com/windows/win32/taskschd/task-scheduler-error-and-success-constants pour ce code" }
            }
        )
        Write-KeyValue "Prochaine exécution" $info.NextRunTime
        Write-KeyValue "Nombre d'exécutions manquées" $info.NumberOfMissedRuns
    }
}

# ----------------------------------------------------------------------------
Write-Section "6. Dossiers de sauvegarde"
# ----------------------------------------------------------------------------
Write-Host "  (Le chemin exact est configuré dans StockManager : Paramètres > Sauvegardes."
Write-Host "   Ce script ne peut pas le lire sans ouvrir la base ; vérifiez-le manuellement"
Write-Host "   si le dossier ci-dessous ne correspond pas à votre configuration réelle.)"
$LikelyBackupDirs = @(
    (Join-Path $env:USERPROFILE "StockManager\Sauvegardes"),
    (Join-Path $env:USERPROFILE "Documents\StockManager\Sauvegardes")
)
foreach ($dir in $LikelyBackupDirs) {
    if (Test-Path $dir) {
        Write-KeyValue "Dossier" $dir
        try {
            $acl = Get-Acl $dir -ErrorAction Stop
            Write-KeyValue "  Propriétaire" $acl.Owner
        } catch {
            Write-KeyValue "  Permissions" "Impossible de les lire : $($_.Exception.Message)"
        }
        $files = Get-ChildItem -Path $dir -Filter "stockmanager_backup*" -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending | Select-Object -First 5
        foreach ($f in $files) {
            Write-Host ("    - {0}  ({1} octets, modifié {2})" -f $f.Name, $f.Length, $f.LastWriteTime)
            $manifest = "$($f.FullName).manifest.json"
            Write-Host ("      Manifeste associé : {0}" -f $(if (Test-Path $manifest) { "présent" } else { "ABSENT" }))
        }
    }
}

# ----------------------------------------------------------------------------
Write-Section "7. Journaux applicatifs StockManager"
# ----------------------------------------------------------------------------
$LogDir = Join-Path $DataDir "logs"
if (Test-Path $LogDir) {
    Write-KeyValue "Dossier de journaux" $LogDir
    $latestLog = Get-ChildItem -Path $LogDir -Filter "*.log" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($latestLog) {
        Write-KeyValue "Journal le plus récent" $latestLog.FullName
        Write-KeyValue "  Modifié le" $latestLog.LastWriteTime
        Write-Host ""
        Write-Host "  -- 60 dernières lignes contenant 'auvegarde' ou 'pg_dump' ou 'pg_restore' ou 'Agent' --"
        Get-Content -Path $latestLog.FullName -Tail 4000 -ErrorAction SilentlyContinue |
            Select-String -Pattern "auvegarde|pg_dump|pg_restore|Agent|schtasks|planifi" |
            Select-Object -Last 60 |
            ForEach-Object { Write-Host "    $_" }
    } else {
        Write-KeyValue "Journal le plus récent" "AUCUN fichier .log trouvé dans ce dossier."
    }
} else {
    Write-KeyValue "Dossier de journaux" "INTROUVABLE ($LogDir) — StockManager a-t-il déjà été lancé sous ce compte ?"
}

# ----------------------------------------------------------------------------
Write-Section "8. Test direct de l'agent auxiliaire (hors tâche planifiée)"
# ----------------------------------------------------------------------------
Write-Host "  Ce script NE LANCE PAS l'agent lui-même (effet non lu : il déclencherait"
Write-Host "  une vraie tentative de sauvegarde). Pour comparer vous-même l'exécution"
Write-Host "  directe à celle de la tâche planifiée, lancez SÉPARÉMENT, StockManager"
Write-Host "  étant complètement fermé :"
Write-Host ""
Write-Host '      & "<chemin StockManager.exe>" --run-backup-agent'
Write-Host ""
Write-Host "  puis consultez immédiatement après le journal applicatif (section 7"
Write-Host "  ci-dessus) : la toute première ligne attendue est désormais"
Write-Host "  « Agent de sauvegarde : démarrage du cycle, tentative d'acquisition du"
Write-Host "  verrou. » — son absence prouve que l'agent n'a pas démarré du tout"
Write-Host "  (commande/chemin de la tâche planifiée en cause, voir section 5) plutôt"
Write-Host "  qu'un cycle démarré puis sans effet pour une autre raison."

# ----------------------------------------------------------------------------
Stop-Transcript | Out-Null
Write-Host ""
Write-Host "Diagnostic enregistré dans : $TranscriptPath" -ForegroundColor Green
