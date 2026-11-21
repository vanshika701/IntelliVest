"""Unit tests for the summarization package: each extractive step, the
word-limit guarantee, the factory and batch error isolation."""

import pytest

from app.core.config import settings
from app.services.summarization import SummaryFailure, SummaryInput, SummaryResult, get_summarizer
from app.services.summarization.base import Summarizer
from app.services.summarization.evaluation import rouge_l, rouge_n, rouge_scores
from app.services.summarization.extractive import (
    CONFIG,
    ExtractiveSummarizer,
    clean_text,
    jaccard,
    score_sentence,
    select_sentences,
    split_sentences,
    tokenize,
    word_weights,
)
from app.services.summarization.ml import MlSummarizer
from app.services.summarization.textutils import count_words, trim_to_words

ARTICLE = (
    "Infosys reported a 7.5% rise in net profit to Rs. 7,364 crore for the September quarter, beating estimates. "
    "Revenue grew 4.2% year-on-year to Rs. 44,490 crore, helped by large deal wins in financial services. "
    "The company raised its FY27 revenue growth guidance to 3-3.5% in constant currency. "
    "Mr. Salil Parekh, CEO, said demand for AI-led transformation programmes remained strong. "
    "Shares of the company closed 1.2% higher on the NSE ahead of the results. "
    "Analysts at several brokerages expect margins to stay in a narrow band through the next two quarters. "
    "Infosys posted a 7.5% increase in net profit to Rs. 7,364 crore for the quarter ended September. "
    "Click here to subscribe to our newsletter for more updates. "
    "Attrition in the IT services industry eased slightly during the period, according to industry trackers. "
    "The board also declared an interim dividend of Rs. 21 per share, with a record date later this month. "
    "Large rivals including TCS and Wipro are scheduled to report their numbers over the coming weeks."
)


def summarize(text: str, title: str = "Infosys Q2 profit rises 7.5%", max_words: int = 100, name: str | None = "Infosys"):
    return ExtractiveSummarizer().summarize(SummaryInput(title=title, text=text, max_words=max_words, instrument_name=name))


# --- Step 1: cleaning ----------------------------------------------------------

def test_clean_text_strips_html_entities_and_boilerplate_lines() -> None:
    raw = (
        "<div><p>Infosys shares rose 2% &amp; hit a record.</p><script>track()</script>"
        "<p>Subscribe to our newsletter</p><p>Read more: Top stocks today</p></div>"
    )
    assert clean_text(raw) == "Infosys shares rose 2% & hit a record."
    assert clean_text("Gold   prices\n\n rose ") == "Gold prices. rose."


def test_clean_text_strips_urls() -> None:
    text = "Shares fell 2.5%. https://www.example.com/stocks/infosys-ltd/ By noon the stock recovered."
    assert clean_text(text) == "Shares fell 2.5%. By noon the stock recovered."


def test_clean_text_keeps_headings_from_merging_into_the_next_sentence() -> None:
    text = "Infosys will invest $10 million in the venture.\nJapan Expansion\nAs part of the deal, it gets a board seat."
    assert split_sentences(clean_text(text)) == [
        "Infosys will invest $10 million in the venture.",
        "Japan Expansion.",
        "As part of the deal, it gets a board seat.",
    ]


def test_clean_text_collapses_whitespace_and_handles_empty() -> None:
    assert clean_text("  Gold   prices   rose  ") == "Gold prices rose"
    assert clean_text(None) == ""
    assert clean_text("") == ""


# --- Step 2: sentence splitting ---------------------------------------------------

def test_split_sentences_keeps_abbreviations_decimals_and_currency_together() -> None:
    text = (
        "Profit rose 7.5% to Rs. 1,200 crore. Mr. Rao said margins held, e.g. in banking. "
        "Shares hit Rs. 2,450.50 on Monday. Reliance Industries Ltd. reported strong numbers."
    )
    assert split_sentences(text) == [
        "Profit rose 7.5% to Rs. 1,200 crore.",
        "Mr. Rao said margins held, e.g. in banking.",
        "Shares hit Rs. 2,450.50 on Monday.",
        "Reliance Industries Ltd. reported strong numbers.",
    ]


def test_split_sentences_handles_questions_quotes_and_initials() -> None:
    text = 'Is gold still a hedge? "Yes," said N. R. Narayana Murthy. The U.S. Fed held rates.'
    assert split_sentences(text) == ['Is gold still a hedge?', '"Yes," said N. R. Narayana Murthy.', 'The U.S. Fed held rates.']


def test_split_sentences_empty() -> None:
    assert split_sentences("") == []


# --- Step 3: tokenizing -----------------------------------------------------------

def test_tokenize_lowercases_and_drops_stop_words() -> None:
    assert tokenize("The Profit of Infosys rose by 7.5% in the quarter") == ["profit", "infosys", "rose", "7.5", "quarter"]


# --- Steps 4-5: weighting and scoring -------------------------------------------

def test_word_weights_boost_title_and_instrument_words() -> None:
    sentences = [["profit", "rose"], ["revenue", "rose"], ["infosys", "deal"]]
    plain = word_weights(sentences, set(), set())
    boosted = word_weights(sentences, {"profit"}, {"infosys"})
    # Equal frequency without boosts; the title word wins once boosted.
    assert plain["profit"] == plain["revenue"]
    assert boosted["profit"] > boosted["revenue"]
    assert boosted["infosys"] == 1.0  # instrument word gets the top weight
    assert max(plain.values()) == 1.0


def test_score_sentence_applies_position_number_and_penalties() -> None:
    weights = {"profit": 1.0, "rose": 0.5, "company": 0.5, "stated": 0.2, "result": 0.3, "today": 0.2}
    tokens = ["profit", "rose", "company", "stated", "result", "today"]
    sentence = "The company stated profit rose in the result today."
    first = score_sentence(0, sentence, tokens, weights, set())
    later = score_sentence(5, sentence, tokens, weights, set())
    assert first == pytest.approx(later + CONFIG.position_bonus[0])

    with_number = score_sentence(5, sentence + " It rose 5%.", tokens, weights, set())
    assert with_number > later

    short = score_sentence(5, "Profit rose.", ["profit", "rose"], weights, set())
    assert short < score_sentence(5, "Profit rose sharply for the company in the latest quarter.", ["profit", "rose"], weights, set())

    boilerplate = score_sentence(5, "Subscribe to our newsletter for profit updates today.", tokens, weights, set())
    assert boilerplate < later * 0.2


# --- Steps 6-7: selection ---------------------------------------------------------

def test_select_sentences_skips_near_duplicates_and_keeps_original_order() -> None:
    sentences = [
        "Alpha beta gamma delta epsilon zeta.",  # 0 — low score
        "Infosys profit rose sharply this quarter on deal wins.",  # 1 — best
        "Infosys profit rose sharply this quarter on large deal wins.",  # 2 — near-duplicate of 1
        "Revenue guidance was raised for the full year.",  # 3 — second best
    ]
    token_sets = [set(tokenize(s)) for s in sentences]
    scores = [0.1, 0.9, 0.85, 0.6]
    assert select_sentences(sentences, scores, token_sets, max_words=100) == [1, 3]


def test_select_sentences_respects_word_budget() -> None:
    sentences = ["one two three four five six.", "seven eight nine ten eleven twelve.", "a b c d e f g h i j."]
    token_sets = [set(tokenize(s)) for s in sentences]
    assert select_sentences(sentences, [0.9, 0.8, 0.7], token_sets, max_words=12) == [0, 1]


def test_jaccard() -> None:
    assert jaccard({"a", "b"}, {"a", "b"}) == 1.0
    assert jaccard({"a"}, {"b"}) == 0.0
    assert jaccard(set(), {"a"}) == 0.0


# --- Step 8: the word limit ------------------------------------------------------------

def test_trim_to_words_prefers_clause_boundary() -> None:
    text = "Gold rose to a record, driven by central bank buying and a weaker dollar across markets"
    # Clause boundary after 5 words is kept when it retains >= 60% of the limit...
    assert trim_to_words(text, 8) == "Gold rose to a record…"
    # ...otherwise the cut happens at the word boundary.
    assert trim_to_words(text, 10) == "Gold rose to a record, driven by central bank buying…"
    assert count_words(trim_to_words(text, 10)) <= 10


def test_trim_to_words_falls_back_to_word_boundary() -> None:
    text = "one two three four five six seven eight nine ten eleven"
    assert trim_to_words(text, 5) == "one two three four five…"
    assert trim_to_words("short text", 5) == "short text"
    assert trim_to_words("anything", 0) == ""


@pytest.mark.parametrize("max_words", [100, 40, 15])
def test_full_article_summary_respects_limit_and_reads_in_order(max_words: int) -> None:
    result = summarize(ARTICLE, max_words=max_words)
    assert 0 < result.word_count <= max_words
    assert result.word_count == count_words(result.summary)
    assert "subscribe" not in result.summary.lower()
    # Picked sentences appear in their original order.
    positions = [ARTICLE.find(s) for s in split_sentences(result.summary) if s in ARTICLE]
    assert positions == sorted(positions)


def test_summary_skips_the_duplicated_profit_sentence() -> None:
    result = summarize(ARTICLE)
    assert result.summary.count("net profit") + result.summary.count("increase in net profit") <= 1


def test_one_very_long_sentence_is_trimmed_cleanly() -> None:
    long_sentence = "The company said " + ", ".join(f"segment {i} grew steadily" for i in range(60)) + "."
    result = summarize(long_sentence + " " + long_sentence.replace("company", "firm"), max_words=100)
    assert result.word_count <= 100
    assert result.summary.endswith(("…", "."))


def test_short_snippet_is_returned_as_is() -> None:
    snippet = "Infosys signed a $1.5 billion deal with a European bank, its largest this year. Shares rose 2% on the news."
    assert summarize(snippet).summary == snippet


def test_article_is_longer_than_the_limit() -> None:
    assert count_words(ARTICLE) > 100


def test_low_scoring_filler_is_not_added_just_because_there_is_room() -> None:
    result = summarize(ARTICLE, max_words=100)
    assert len(split_sentences(result.summary)) <= CONFIG.max_sentences


def test_empty_text_falls_back_to_headline() -> None:
    result = summarize("", title="Infosys wins <b>$1.5 billion</b> deal")
    assert result.summary == "Infosys wins $1.5 billion deal"


def test_headline_only_longer_than_limit_is_trimmed() -> None:
    title = " ".join(["word"] * 30)
    assert summarize("", title=title, max_words=10).word_count <= 10


def test_result_metadata() -> None:
    result = summarize(ARTICLE)
    assert result.provider == "extractive"
    assert result.method.startswith("tfidf-extractive@")
    assert result.latency_ms >= 0


# --- Factory, ML placeholder, batch isolation --------------------------------------------

def test_factory_selects_implementation(monkeypatch: pytest.MonkeyPatch) -> None:
    assert isinstance(get_summarizer(), ExtractiveSummarizer)
    assert isinstance(get_summarizer("ML"), MlSummarizer)
    monkeypatch.setattr(settings, "summarizer_provider", "ml")
    assert get_summarizer().provider == "ml"
    with pytest.raises(ValueError, match="Unknown SUMMARIZER_PROVIDER"):
        get_summarizer("gpt")


def test_ml_summarizer_is_a_placeholder() -> None:
    with pytest.raises(NotImplementedError):
        get_summarizer("ml").summarize(SummaryInput(title="t", text="x"))


def test_batch_isolates_failures() -> None:
    class Flaky(Summarizer):
        provider = "flaky"
        method = "flaky@1"

        def summarize(self, item: SummaryInput) -> SummaryResult:
            if "boom" in item.title:
                raise RuntimeError("model exploded")
            return SummaryResult(item.title, 1, self.provider, self.method, 0.0)

    items = [SummaryInput(title=t, text="", url=f"u{i}") for i, t in enumerate(["ok1", "boom", "ok3", "ok4", "ok5"])]
    results = Flaky().summarize_batch(items)
    assert [type(r).__name__ for r in results] == ["SummaryResult", "SummaryFailure", "SummaryResult", "SummaryResult", "SummaryResult"]
    assert isinstance(results[1], SummaryFailure)
    assert results[1].error == "model exploded" and results[1].url == "u1"


def test_ml_batch_fails_every_item_without_raising() -> None:
    results = get_summarizer("ml").summarize_batch([SummaryInput(title="a", text="b"), SummaryInput(title="c", text="d")])
    assert all(isinstance(r, SummaryFailure) for r in results)


# --- ROUGE ----------------------------------------------------------------------------

def test_rouge_scores_match_hand_computed_values() -> None:
    reference = "the cat sat on the mat"
    candidate = "the cat lay on the mat"
    assert rouge_n(candidate, reference, 1) == pytest.approx(5 / 6)
    assert rouge_n(candidate, reference, 2) == pytest.approx(3 / 5)
    assert rouge_l(candidate, reference) == pytest.approx(5 / 6)
    assert rouge_scores(reference, reference) == {"rouge1": 1.0, "rouge2": 1.0, "rougeL": 1.0}
    assert rouge_scores("", reference)["rouge1"] == 0.0


# --- Evaluation harness -----------------------------------------------------------------

def test_evaluate_reports_compliance_latency_compression_and_rouge() -> None:
    from app.services.summarization.evaluation import evaluate

    records = [
        {"url": "u1", "title": "Infosys Q2 profit rises 7.5%", "article_text": ARTICLE},
        {"url": "u2", "title": "Gold hits record", "article_text": ""},
    ]
    references = {"u1": "Infosys net profit rose 7.5% to Rs 7,364 crore in the September quarter."}
    report = evaluate(get_summarizer("extractive"), records, 100, references)
    assert report["items"] == 2 and report["failures"] == 0
    assert report["word_limit_compliance"] == 1.0
    assert 0 < report["compression_ratio_avg"] < 1
    assert report["latency_ms_avg"] >= 0
    assert report["rouge_items"] == 1 and 0 < report["rouge1"] <= 1


def test_evaluate_counts_failures_for_the_ml_placeholder() -> None:
    from app.services.summarization.evaluation import evaluate

    report = evaluate(get_summarizer("ml"), [{"url": "u", "title": "t", "article_text": "x"}], 100)
    assert report == {"provider": "ml", "method": "ml-model@unreleased", "max_words": 100, "items": 1, "failures": 1}


# --- Multi-document input (combined summary of several articles) -------------------------

DOCS = (
    (
        "Reliance promoters bought 4.26 lakh shares in open-market purchases. The stock has rallied 13% this month. "
        "Analysts see further upside as refining margins improve."
    ),
    (
        "JPMorgan sees 23% upside in Reliance Industries to Rs 1,675 on better earnings. The broker raised estimates. "
        "It cited strong retail growth."
    ),
    (
        "Reliance plans to invest Rs 15,000 crore in 100 biogas plants by 2030. The plants will use farm waste. "
        "Construction starts next year."
    ),
)


def test_document_sentences_resets_position_per_document() -> None:
    from app.services.summarization.extractive import document_sentences

    sentences, positions = document_sentences(DOCS)
    assert positions == [0, 1, 2, 0, 1, 2, 0, 1, 2]
    assert sentences[3].startswith("JPMorgan")


def test_multi_document_summary_covers_several_articles_one_sentence_each() -> None:
    result = ExtractiveSummarizer().summarize(
        SummaryInput(title="Reliance", text="\n".join(DOCS), documents=DOCS, instrument_name="Reliance")
    )
    summary = result.summary
    assert result.word_count <= 100
    # Each article's lead makes it in, in document order; never two from one article.
    assert [s.split()[0] for s in split_sentences(summary)] == ["Reliance", "JPMorgan", "Reliance"]
    assert "rallied 13%" not in summary


def test_paraphrased_sentences_across_articles_count_as_duplicates() -> None:
    from app.services.summarization.extractive import is_near_duplicate

    a = set(tokenize("Infosys will invest JPY 1.59 billion for a 10.1% stake in NTT Docomo Playspace"))
    b = set(tokenize("Infosys is acquiring a 10.1% stake in NTT Docomo Playspace to build a metaverse"))
    c = set(tokenize("Infosys shares fell 2% on weak IT demand"))
    assert jaccard(a, b) < CONFIG.duplicate_jaccard_threshold  # Jaccard alone misses it
    assert is_near_duplicate(a, b)
    assert not is_near_duplicate(a, c)


def test_clean_text_unwraps_markdown_links() -> None:
    assert clean_text("[Infosys](https://www.infosys.com) signed a deal.") == "Infosys signed a deal."


def test_questions_are_penalised_and_headlines_get_full_stops() -> None:
    from app.services.summarization.extractive import end_sentence

    weights = {"bank": 1.0, "visit": 0.5, "today": 0.5, "holiday": 0.5, "planning": 0.5, "customers": 0.5}
    tokens = ["planning", "visit", "bank", "today", "holiday", "customers"]
    question = score_sentence(3, "Planning to visit a bank today, customers, on this holiday?", tokens, weights, set())
    statement = score_sentence(3, "Planning to visit a bank today, customers, on this holiday.", tokens, weights, set())
    assert question == pytest.approx(statement * CONFIG.question_multiplier)
    assert end_sentence("Titan shares fall 5%") == "Titan shares fall 5%."
    assert end_sentence("Gold rallies.") == "Gold rallies."
    assert end_sentence("Gold rallies…") == "Gold rallies…"


def test_evaluate_uses_logged_documents_for_multi_article_records() -> None:
    from app.services.summarization.evaluation import evaluate

    record = {"url": "digest-1", "title": "Reliance", "article_text": "\n".join(DOCS), "documents": list(DOCS)}
    report = evaluate(get_summarizer("extractive"), [record], 100)
    assert report["failures"] == 0 and report["word_limit_compliance"] == 1.0
