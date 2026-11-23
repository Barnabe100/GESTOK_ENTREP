from app.views.article_search_panel import ArticleSearchPanel

_ARTICLES = [(10, "ART-001 — Eau minérale 1.5L — 500"), (20, "ART-002 — Riz 25kg — 12000")]


def test_shows_all_articles_when_search_is_empty(qtbot) -> None:
    panel = ArticleSearchPanel(_ARTICLES)
    qtbot.addWidget(panel)

    assert panel.results_list.count() == 2


def test_filters_results_case_insensitively(qtbot) -> None:
    panel = ArticleSearchPanel(_ARTICLES)
    qtbot.addWidget(panel)

    panel.search_edit.setText("riz")

    assert panel.results_list.count() == 1
    assert "Riz" in panel.results_list.item(0).text()


def test_shows_message_when_nothing_matches(qtbot) -> None:
    panel = ArticleSearchPanel(_ARTICLES)
    qtbot.addWidget(panel)

    panel.search_edit.setText("introuvable")

    assert panel.results_list.count() == 1
    item = panel.results_list.item(0)
    assert "Aucun article" in item.text()
    assert not (item.flags() & item.flags().ItemIsSelectable)


def test_double_clicking_result_emits_article_activated(qtbot) -> None:
    panel = ArticleSearchPanel(_ARTICLES)
    qtbot.addWidget(panel)
    received = []
    panel.article_activated.connect(received.append)

    panel._on_item_activated(panel.results_list.item(0))

    assert received == [10]


def test_double_clicking_no_match_message_does_not_emit(qtbot) -> None:
    panel = ArticleSearchPanel(_ARTICLES)
    qtbot.addWidget(panel)
    panel.search_edit.setText("introuvable")
    received = []
    panel.article_activated.connect(received.append)

    panel._on_item_activated(panel.results_list.item(0))

    assert received == []


def test_clear_search_resets_filter(qtbot) -> None:
    panel = ArticleSearchPanel(_ARTICLES)
    qtbot.addWidget(panel)
    panel.search_edit.setText("riz")

    panel.clear_search()

    assert panel.search_edit.text() == ""
    assert panel.results_list.count() == 2


def test_set_articles_updates_results(qtbot) -> None:
    panel = ArticleSearchPanel(_ARTICLES)
    qtbot.addWidget(panel)

    panel.set_articles([(30, "ART-003 — Nouveau — 100")])

    assert panel.results_list.count() == 1
    assert "ART-003" in panel.results_list.item(0).text()


# -- Mission 5.4, Évolution A.1 : 5 résultats visibles sans défilement --------------

_MANY_ARTICLES = [(i, f"ART-{i:03d} — Article {i}") for i in range(1, 11)]


def test_results_list_height_fits_five_rows(qtbot) -> None:
    panel = ArticleSearchPanel(_MANY_ARTICLES)
    qtbot.addWidget(panel)
    panel.show()

    row_height = panel.results_list.sizeHintForRow(0)
    assert row_height > 0
    # Hauteur fixe pour 5 lignes (+ petite marge) — ni plus ni moins, voir
    # apply_comfortable_list_height.
    assert panel.results_list.height() == 5 * row_height + 6


def test_no_vertical_scroll_with_five_or_fewer_results(qtbot) -> None:
    panel = ArticleSearchPanel(_MANY_ARTICLES[:5])
    qtbot.addWidget(panel)
    panel.show()

    assert panel.results_list.count() == 5
    assert panel.results_list.verticalScrollBar().isVisible() is False


def test_vertical_scroll_available_beyond_five_results(qtbot) -> None:
    panel = ArticleSearchPanel(_MANY_ARTICLES)
    qtbot.addWidget(panel)
    panel.show()

    assert panel.results_list.count() == 10
    assert panel.results_list.verticalScrollBar().isVisible() is True


def test_live_filtering_still_works_with_larger_list(qtbot) -> None:
    panel = ArticleSearchPanel(_MANY_ARTICLES)
    qtbot.addWidget(panel)

    panel.search_edit.setText("005")

    assert panel.results_list.count() == 1
    assert "ART-005" in panel.results_list.item(0).text()


def test_double_click_still_adds_article_with_larger_list(qtbot) -> None:
    panel = ArticleSearchPanel(_MANY_ARTICLES)
    qtbot.addWidget(panel)
    received = []
    panel.article_activated.connect(received.append)

    panel._on_item_activated(panel.results_list.item(7))

    assert received == [8]
