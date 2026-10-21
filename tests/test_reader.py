import pytest

import app as nook
import news
import proxy
import reader


@pytest.fixture
def client():
    nook.cache.clear()
    nook.hits.clear()
    reader._cache.clear()
    return nook.app.test_client()


def test_paragraphs_from_feed_html():
    html = "<p>One <b>bold</b> thing.</p><h2>Heading</h2><ul><li>item</li></ul><blockquote><p>quoted</p></blockquote><script>x()</script>"
    assert reader.paragraphs(html) == ["One bold thing.", "Heading", "item", "quoted"]
    assert reader.paragraphs("") == []


def test_extracts_the_article_from_a_page():
    body = "".join(f"<p>Sentence number {i} of a fairly ordinary news article about things.</p>" for i in range(30))
    page = f"<html><body><nav>menu menu</nav><article><h1>Title</h1>{body}</article><footer>cookies</footer></body></html>"
    paras = reader.from_page(page, "https://example.com/a")
    assert reader.size(paras) > 600 and "menu" not in " ".join(paras)


def test_story_links_go_to_the_reader_not_the_source(client, monkeypatch):
    s = news.Story("headline", "https://src.example/story", "BBC", "centre")

    async def fake(selected):
        return [[s]], []

    monkeypatch.setattr(nook, "ask_news", fake)
    html = client.get("/news?w=centre").get_data(as_text=True)
    assert 'href="/read?u=' in html and 'href="https://src.example/story"' not in html


def test_read_needs_a_valid_signature(client):
    assert client.get("/read?u=https://example.com/a").status_code == 403
    assert client.get("/read?u=https://example.com/a&s=" + "0" * 32).status_code == 403
    # a picture signature must not unlock reading
    img_sig = proxy.sign("https://example.com/a")
    assert client.get(f"/read?u=https://example.com/a&s={img_sig}").status_code == 403


def test_read_shows_article_and_source_button(client, monkeypatch):
    s = news.Story("The headline", "https://src.example/story", "BBC", "centre", summary="short")
    monkeypatch.setattr(news, "find", lambda url: s)
    monkeypatch.setattr(reader, "article", lambda url, feed: (["First paragraph.", "Second <b>one</b>."], "page"))
    html = client.get(proxy.read_link(s.url, "left")).get_data(as_text=True)
    assert "The headline" in html and "First paragraph." in html
    assert html.count('href="https://src.example/story"') == 2  # top and bottom buttons
    assert "read at BBC" in html
    assert "Second &lt;b&gt;one&lt;/b&gt;." in html           # escaped, never raw HTML
    assert 'href="/news?w=left"' in html                        # back to the wing you came from


def test_read_falls_back_when_the_page_cannot_be_fetched(client, monkeypatch):
    s = news.Story("Paywalled", "https://src.example/story", "NYT", "left", summary="Only the summary.")
    monkeypatch.setattr(news, "find", lambda url: s)

    def blocked(url):
        raise proxy.Refused("upstream said 403")

    monkeypatch.setattr(proxy, "fetch_page", blocked)
    html = client.get(proxy.read_link(s.url)).get_data(as_text=True)
    assert "Only the summary." in html and "couldn't get the full article" in html
    assert 'href="https://src.example/story"' in html


def test_read_uses_the_feeds_own_text_when_the_page_is_blocked(client, monkeypatch):
    full = "".join(f"<p>Paragraph {i} with enough words to count as real article text here.</p>" for i in range(15))
    s = news.Story("Feed full", "https://src.example/story", "Federalist", "far-right", full=full)
    monkeypatch.setattr(news, "find", lambda url: s)
    monkeypatch.setattr(proxy, "fetch_page", lambda url: (_ for _ in ()).throw(proxy.Refused("403")))
    html = client.get(proxy.read_link(s.url)).get_data(as_text=True)
    assert "Paragraph 3 with enough words" in html and "put in its feed" in html


def test_pictures_only_when_chosen(client, monkeypatch):
    s = news.Story("Pic", "https://src.example/story", "BBC", "centre", image="https://img.example/a.jpg")
    monkeypatch.setattr(news, "find", lambda url: s)
    monkeypatch.setattr(reader, "article", lambda url, feed: (["Text."], "page"))
    assert 'class="lead"' not in client.get(proxy.read_link(s.url)).get_data(as_text=True)
    client.set_cookie("nook_news", "centre|1")
    html = client.get(proxy.read_link(s.url)).get_data(as_text=True)
    assert 'class="lead" src="/img?' in html


def test_page_fetch_refuses_private_addresses():
    with pytest.raises(proxy.Refused):
        proxy.fetch_page("http://127.0.0.1/secret")
    with pytest.raises(proxy.Refused):
        proxy.fetch_page("http://169.254.169.254/latest/meta-data")


def test_a_search_result_can_be_read_in_nook(client, monkeypatch):
    url = "https://blog.example/post"
    monkeypatch.setattr(news, "find", lambda u: None)
    monkeypatch.setattr(reader, "article", lambda u, feed: (["A real paragraph of the post."], "page"))
    html = client.get(proxy.read_link(url, "centre", "python decorators", "Decorators <explained>")).get_data(as_text=True)
    assert "A real paragraph of the post." in html
    assert "Decorators &lt;explained&gt;" in html                      # the title is shown, escaped
    assert 'href="/search?q=python%20decorators"' in html             # back goes to the results
    assert html.count('href="https://blog.example/post"') == 2         # and the source button is there
    assert "/news?w=" not in html                                      # not the news header


def test_web_results_link_to_the_reader(client, monkeypatch):
    from engines import Result

    async def fake(query, page=1, chosen=None, period=None, **kw):
        return [Result(title="A post", url="https://blog.example/post", snippet="s", engines=["bing"], rank=0)], []

    monkeypatch.setattr(nook, "ask", fake)
    html = client.get("/search?q=decorators").get_data(as_text=True)
    assert 'href="/read?u=https%3A%2F%2Fblog.example%2Fpost' in html and ">read</a>" in html
    assert "q=decorators" in html.split("/read?u=")[1].split('"')[0]


# --- reader tools ---------------------------------------------------------------

def test_reading_time_and_tools(client, monkeypatch):
    s = news.Story("Long one", "https://src.example/long", "BBC", "centre")
    monkeypatch.setattr(news, "find", lambda url: s)
    words = " ".join(["word"] * 700)                       # about three minutes at 230 a minute
    monkeypatch.setattr(reader, "article", lambda url, feed: ([words, "Short."], "page"))
    html = client.get(proxy.read_link(s.url)).get_data(as_text=True)
    assert "3 min read" in html and 'data-act="bigger"' in html and 'data-act="listen"' in html and "reader.js" in html
    title = html.split("<title>")[1].split("</title>")[0]
    assert title == "Long one - nook"                                    # nothing but the title in the title
    assert html.index("</article>") < html.index("reader.js")             # the script comes after the article
    monkeypatch.setattr(reader, "article", lambda url, feed: (["Tiny."], "page"))
    assert "1 min read" in client.get(proxy.read_link(s.url)).get_data(as_text=True)   # never "0 min"


def test_no_tools_when_the_article_could_not_be_fetched(client, monkeypatch):
    s = news.Story("Paywalled", "https://src.example/p", "NYT", "left", summary="Only this.")
    monkeypatch.setattr(news, "find", lambda url: s)
    monkeypatch.setattr(reader, "article", lambda url, feed: ([], "partial"))
    html = client.get(proxy.read_link(s.url)).get_data(as_text=True)
    assert "min read" not in html and "reader.js" not in html
