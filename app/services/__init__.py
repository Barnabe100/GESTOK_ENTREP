"""Couche services (cas d'usage métier).

Volontairement vide à ce stade (Phase 1 - socle technique). Les services
métier (StockService, SalesService, PurchaseService, ExitService,
InventoryService, LicenseService, BackupService, ...) seront ajoutés phase
par phase, en s'appuyant sur les repositories définis dans
``app.repositories`` et jamais directement sur une session SQLAlchemy
exposée à la couche vue.
"""
