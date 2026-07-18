import streamlit as st
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from io import BytesIO
from pypdf import PdfReader
from docx import Document
import tempfile
import subprocess
import os


# ======================
# SESSION STATE
# ======================

if "article" not in st.session_state:
    st.session_state.article = ""

if "title_tag" not in st.session_state:
    st.session_state.title_tag = ""

if "meta_description" not in st.session_state:
    st.session_state.meta_description = ""

if "excerpt" not in st.session_state:
    st.session_state.excerpt = ""

if "faq" not in st.session_state:
    st.session_state.faq = ""

if "article_title" not in st.session_state:
    st.session_state.article_title = ""

if "wordpress_post_id" not in st.session_state:
    st.session_state.wordpress_post_id = None

if "wordpress_edit_url" not in st.session_state:
    st.session_state.wordpress_edit_url = ""


NARRATIVE_STRUCTURES = {
    "Nessuna struttura predefinita": """
Segui la struttura emersa dall'analisi dei competitor e delle PAA senza imporre una gabbia narrativa artificiale.
Usa solo gli elementi veramente supportati dai dati disponibili.
""".strip(),
    "La struttura investigativa (Whodunit)": """
Costruisci il testo come un'indagine progressiva.
Ordine consigliato: il crimine, raccolta delle prove, sospetti, falsi indizi, svolta decisiva, arresto o soluzione, processo ed epilogo.
Ogni sezione deve rispondere a una domanda e aprire il passaggio successivo.
""".strip(),
    "La struttura cronologica": """
Racconta gli eventi nell'ordine in cui sono accaduti.
Ordine consigliato: contesto iniziale, vita della vittima, vita dell'autore, eventi precedenti, il crimine, indagini, processo, conseguenze.
Privilegia chiarezza, linearita' e orientamento temporale.
""".strip(),
    "La struttura 'conosciamo gia il colpevole'": """
Rendi noto fin dall'inizio chi ha commesso il delitto.
La tensione deve ruotare attorno a perche', come ci e' riuscito e perche' non e' stato fermato prima.
Valorizza psicologia criminale, modus operandi, falle investigative e contesto.
""".strip(),
    "La struttura 'come siamo arrivati fin qui'": """
Apri con il momento piu drammatico o con il punto di massima tensione.
Poi torna indietro e ricostruisci gli eventi che hanno portato a quel momento.
Chiudi riallacciandoti al presente narrativo e alle conseguenze.
""".strip(),
    "La struttura a puzzle": """
Organizza il racconto in blocchi che inizialmente sembrano parziali o scollegati.
Ogni sezione deve aggiungere un elemento rilevante fino a far emergere il quadro completo verso la fine.
Mantieni alta la leggibilita' con segnali chiari e transizioni forti.
""".strip(),
    "La struttura centrata sulla vittima": """
Il fulcro del racconto deve essere la vittima.
Dedica spazio a identita', relazioni, aspirazioni, contesto di vita e impatto della perdita.
Evita di glorificare il colpevole e tratta il crimine come parte di una storia umana piu ampia.
""".strip(),
    "La struttura psicologica": """
Dai priorita' all'analisi della personalita' del colpevole, delle dinamiche familiari, della manipolazione, dell'escalation e delle motivazioni.
L'indagine puo' restare sullo sfondo, ma deve sostenere l'analisi comportamentale.
Usa un tono rigoroso e non sensazionalistico.
""".strip(),
    "La struttura corale": """
Racconta la vicenda attraverso piu punti di vista: investigatori, giornalisti, parenti, amici, avvocati, testimoni.
Ogni prospettiva deve aggiungere informazioni o cambiare l'interpretazione dei fatti.
Mantieni sempre chiaro chi sta osservando cosa.
""".strip(),
    "La struttura 'cold case'": """
Alterna passato e presente investigativo.
Metti in evidenza nuove prove, riletture del caso, tecnologie moderne e riaperture investigative.
Il conflitto narrativo principale deve essere il tempo e cio' che ha cancellato o trasformato.
""".strip(),
    "La struttura documentaristica": """
Segui un'impostazione giornalistica e documentale.
Privilegia contesto, fatti verificati, fonti, documenti, interviste e conclusioni ragionate.
La credibilita' deve venire prima della suspense.
""".strip(),
}


# ======================
# SERPER ORGANIC RESULTS
# ======================

def format_http_error(service_name: str, response: requests.Response | None):
    if response is None:
        return f"{service_name}: nessuna risposta ricevuta dall'API."

    status_code = response.status_code
    detail = ""

    try:
        payload = response.json()
        if isinstance(payload, dict):
            detail = (
                payload.get("message")
                or payload.get("error")
                or payload.get("errors")
                or ""
            )
        else:
            detail = str(payload)
    except ValueError:
        detail = response.text.strip()

    if isinstance(detail, list):
        detail = ", ".join(str(item) for item in detail)

    detail = str(detail).strip()
    if len(detail) > 300:
        detail = f"{detail[:297]}..."

    detail_lower = detail.lower()

    if "not enough credits" in detail_lower:
        return (
            f"{service_name} ha restituito HTTP {status_code}. "
            f"Dettaglio: {detail} Hai esaurito i crediti disponibili su {service_name}."
        )

    hints = {
        400: "Verifica keyword, country code e language code inviati alla richiesta.",
        401: "Controlla che la API key sia corretta e attiva.",
        403: "La API key potrebbe non avere i permessi necessari oppure l'account potrebbe essere bloccato.",
        429: "Hai probabilmente raggiunto il rate limit o terminato i crediti disponibili.",
        500: "Errore temporaneo del provider. Riprova tra qualche minuto.",
    }

    message = f"{service_name} ha restituito HTTP {status_code}."
    if detail:
        message = f"{message} Dettaglio: {detail}"

    hint = hints.get(status_code)
    if hint:
        message = f"{message} {hint}"

    return message

def get_competitors(keyword: str, num_results: int, serper_key: str, hl: str, gl: str):
    url = "https://google.serper.dev/search"

    headers = {
        "X-API-KEY": serper_key,
        "Content-Type": "application/json"
    }

    competitors = []
    seen_urls = set()
    start = 0

    blocked_domains = [
        "youtube.com",
        "youtu.be",
        "tiktok.com",
        "instagram.com",
        "facebook.com",
        "pinterest.com"
    ]

    while len(competitors) < num_results and start <= 90:
        payload = {
            "q": keyword,
            "gl": gl,
            "hl": hl,
            "num": 10,
            "start": start
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(format_http_error("Serper", exc.response)) from exc
        except requests.RequestException as exc:
            raise RuntimeError(f"Serper: richiesta fallita. Dettaglio: {exc}") from exc

        data = response.json()

        organic = data.get("organic", [])
        if not organic:
            break

        for item in organic:
            link = item.get("link")

            if not link:
                continue

            normalized_link = link.strip().rstrip("/")

            if any(domain in normalized_link for domain in blocked_domains):
                continue

            if normalized_link in seen_urls:
                continue

            seen_urls.add(normalized_link)

            competitors.append({
                "title": item.get("title", ""),
                "link": normalized_link
            })

            if len(competitors) >= num_results:
                break

        start += 10

    return competitors[:num_results]


# ======================
# PEOPLE ALSO ASK
# ======================

def get_people_also_ask(keyword: str, serpapi_key: str, hl: str, gl: str):
    url = "https://serpapi.com/search.json"

    params = {
        "engine": "google",
        "q": keyword,
        "hl": hl,
        "gl": gl,
        "api_key": serpapi_key
    }

    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise RuntimeError(format_http_error("SerpAPI", exc.response)) from exc
    except requests.RequestException as exc:
        raise RuntimeError(f"SerpAPI: richiesta fallita. Dettaglio: {exc}") from exc

    data = response.json()

    questions = []
    seen = set()

    for item in data.get("related_questions", []):
        q = item.get("question")
        if not q:
            continue

        clean_q = q.strip()
        if clean_q in seen:
            continue

        seen.add(clean_q)
        questions.append(clean_q)

    return questions[:10]


# ======================
# SCRAPING PAGINA
# ======================

def fetch_page(url: str):
    try:
        resp = requests.get(
            url,
            timeout=15,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            }
        )
        resp.raise_for_status()

        html = resp.text
        soup = BeautifulSoup(html, "html.parser")

        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        text = " ".join(soup.get_text().split())

        return html, text[:18000]

    except Exception:
        return "", ""


def extract_metadata(html: str):
    soup = BeautifulSoup(html, "html.parser")

    title = soup.title.string.strip() if soup.title and soup.title.string else ""

    h1_tag = soup.find("h1")
    h1 = h1_tag.get_text(strip=True) if h1_tag else ""

    meta_desc = ""
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and "content" in meta.attrs:
        meta_desc = meta["content"].strip()

    return title, h1, meta_desc


def extract_text_from_uploaded_file(uploaded_file):
    file_name = uploaded_file.name or "documento"
    file_extension = os.path.splitext(file_name)[1].lower()

    try:
        if file_extension == ".pdf":
            reader = PdfReader(BytesIO(uploaded_file.getvalue()))
            pages = []

            for page in reader.pages:
                pages.append((page.extract_text() or "").strip())

            return " ".join([page for page in pages if page]).strip()

        if file_extension == ".docx":
            document = Document(BytesIO(uploaded_file.getvalue()))
            paragraphs = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]
            return "\n".join(paragraphs).strip()

        if file_extension == ".doc":
            with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_file:
                temp_file.write(uploaded_file.getvalue())
                temp_path = temp_file.name

            try:
                result = subprocess.run(
                    ["textutil", "-convert", "txt", "-stdout", temp_path],
                    capture_output=True,
                    text=True,
                    check=True
                )
                return result.stdout.strip()
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
    except Exception:
        return ""

    return ""


def build_uploaded_documents_context(uploaded_files):
    if not uploaded_files:
        return ""

    document_blocks = []

    for uploaded_file in uploaded_files:
        text = extract_text_from_uploaded_file(uploaded_file)
        if not text:
            continue

        document_blocks.append(
            f"DOCUMENTO: {uploaded_file.name}\nCONTENUTO:\n{text[:18000]}"
        )

    return "\n\n-------------------------\n\n".join(document_blocks)


def parse_generated_content(content: str):
    def extract_section(text: str, start_marker: str, end_markers: list[str]):
        if start_marker not in text:
            return ""

        section = text.split(start_marker, 1)[1]
        end_positions = [section.find(marker) for marker in end_markers if marker in section]
        end_positions = [position for position in end_positions if position >= 0]

        if end_positions:
            section = section[:min(end_positions)]

        return section.strip()

    title = extract_section(
        content,
        "TITLE TAG:",
        ["META DESCRIPTION:", "EXCERPT:", "FAQ HTML:", "ARTICLE HTML:"]
    )
    meta = extract_section(
        content,
        "META DESCRIPTION:",
        ["EXCERPT:", "FAQ HTML:", "ARTICLE HTML:"]
    )
    excerpt = extract_section(
        content,
        "EXCERPT:",
        ["FAQ HTML:", "ARTICLE HTML:"]
    )
    faq = extract_section(
        content,
        "FAQ HTML:",
        ["ARTICLE HTML:"]
    )
    article = extract_section(
        content,
        "ARTICLE HTML:",
        []
    ) or content.strip()

    return title, meta, excerpt, faq, article


def get_narrative_structure_guidance(structure_name: str):
    return NARRATIVE_STRUCTURES.get(
        structure_name,
        NARRATIVE_STRUCTURES["Nessuna struttura predefinita"]
    )


# ======================
# WORDPRESS
# ======================

def get_secret(section: str, key: str, default: str = ""):
    """Legge un secret senza mostrare credenziali nell'interfaccia o nei log."""
    try:
        return str(st.secrets[section][key]).strip()
    except (KeyError, TypeError, FileNotFoundError):
        return default


def prepare_wordpress_content(article_html: str, faq_html: str) -> str:
    """Rimuove l'H1 dal corpo: WordPress lo genera dal campo title."""
    soup = BeautifulSoup(article_html or "", "html.parser")
    first_h1 = soup.find("h1")
    if first_h1:
        first_h1.decompose()

    article_body = str(soup).strip()
    faq_body = (faq_html or "").strip()

    if faq_body:
        return f"{article_body}\n\n<section class=\"article-faq\">\n<h2>Domande frequenti</h2>\n{faq_body}\n</section>"

    return article_body


def create_wordpress_draft(title: str, article_html: str, excerpt: str, faq_html: str):
    wp_url = get_secret("wordpress", "url").rstrip("/")
    wp_username = get_secret("wordpress", "username")
    wp_password = get_secret("wordpress", "application_password")

    missing = []
    if not wp_url:
        missing.append("wordpress.url")
    if not wp_username:
        missing.append("wordpress.username")
    if not wp_password:
        missing.append("wordpress.application_password")
    if missing:
        raise RuntimeError(
            "Secrets WordPress mancanti: " + ", ".join(missing)
        )

    payload = {
        "title": title.strip(),
        "content": prepare_wordpress_content(article_html, faq_html),
        "excerpt": excerpt.strip(),
        "status": "draft",
    }

    try:
        response = requests.post(
            f"{wp_url}/wp-json/wp/v2/posts",
            auth=(wp_username, wp_password),
            json=payload,
            timeout=45,
        )
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise RuntimeError(format_http_error("WordPress", exc.response)) from exc
    except requests.RequestException as exc:
        raise RuntimeError(f"WordPress: richiesta fallita. Dettaglio: {exc}") from exc

    post = response.json()
    post_id = post.get("id")
    if not post_id:
        raise RuntimeError("WordPress non ha restituito l'ID della bozza creata.")

    return {
        "id": post_id,
        "link": post.get("link", ""),
        "edit_url": f"{wp_url}/wp-admin/post.php?post={post_id}&action=edit",
    }


# ======================
# GENERAZIONE ARTICOLO
# ======================


def generate_article(
    keyword: str,
    article_title: str,
    competitors: list,
    paa: list,
    openai_key: str,
    language: str,
    narrative_structure: str,
    secondary_keywords: str = "",
    custom_prompt: str = "",
    uploaded_documents_context: str = ""
):
    client = OpenAI(api_key=openai_key)

    merged = ""

    for comp in competitors:
        merged += f"""
URL: {comp['link']}

TITLE: {comp['html_title']}
H1: {comp['h1']}
META: {comp['meta_desc']}

CONTENUTO:
{comp['text']}

-------------------------
"""

    paa_block = "\n".join([f"- {q}" for q in paa]) if paa else "Nessuna PAA disponibile."
    secondary_keywords_block = secondary_keywords.strip() or "Nessuna keyword secondaria fornita."
    custom_prompt_block = custom_prompt.strip()
    uploaded_documents_block = uploaded_documents_context.strip() or "Nessun documento aggiuntivo fornito."
    structure_guidance = get_narrative_structure_guidance(narrative_structure)

    prompt = f"""
Sei un giornalista investigativo professionista, criminologo divulgatore ed esperto di SEO editoriale avanzata per contenuti true crime.

Competenze prioritarie:
- cronaca nera
- criminalistica
- criminologia
- psicologia criminale
- serial killer
- cold case
- organizzazioni criminali
- procedure giudiziarie
- SEO editoriale
- GEO
- AI Overviews
- Search Intent Analysis
- Entity SEO

Scrivi un contenuto SEO completo per il tema:

KEYWORD TARGET:
{keyword}

SECONDARY KEYWORDS:
{secondary_keywords_block}

H1 ARTICOLO (da usare obbligatoriamente, non modificarlo):
{article_title}

Language code della ricerca: {language}

STRUTTURA NARRATIVA SELEZIONATA:
{narrative_structure}

ISTRUZIONI SULLA STRUTTURA:
{structure_guidance}

Il risultato deve contenere:

TITLE TAG
META DESCRIPTION
EXCERPT
FAQ HTML
ARTICLE HTML

Vincoli output:
- TITLE TAG: max 60 caratteri, differenziato dall'H1, SEO oriented
- META DESCRIPTION: tra 136 e 155 caratteri, naturale, informativa, con soft CTA se coerente
- EXCERPT: max 160 caratteri, in plain text, senza virgolette
- FAQ HTML: almeno 6 FAQ in HTML, con domanda in <h3> e risposta in <p>
- ARTICLE HTML: 1800-3200 parole, HTML pronto per CMS

Regole HTML:
- L'H1 dell'articolo è già definito e deve essere:
<h1>{article_title}</h1>
- Non creare un nuovo H1
- Inserisci questo H1 all'inizio dell'articolo
- usa <h2> e <h3>
- usa <p>
- usa <ul> <ol>
- usa <strong>
- usa <table> se utile
- NON includere <html> <body>
- NON inserire la sezione FAQ dentro ARTICLE HTML: le FAQ vanno solo nel blocco FAQ HTML

Le PAA non devono essere copiate meccanicamente e non devono comparire come semplice elenco Q&A nell'articolo.

# Requisiti editoriali true crime

- Mantieni un tono giornalistico, investigativo, autorevole e divulgativo.
- Evita sensazionalismo, morbositá gratuita, clickbait e toni spettacolarizzanti.
- Non inventare mai fatti, date, nomi, prove, citazioni, testimonianze o dettagli investigativi non supportati dai materiali forniti.
- Se un punto è controverso o incerto, segnalalo con chiarezza invece di colmarlo con supposizioni.
- Tratta i fatti in modo accurato, contestualizzato e rispettoso delle vittime.
- Usa gli heading (H2, H3) per organizzare risposte chiare a search intent e domande implicite.
- Integra la main keyword nel testo sempre in maniera naturale, mai in modo artificiale o secco, rispettando la grammatica della lingua in cui stai lavorando.
- Non formulare tutti gli headings in forma di domanda, solo se necessario.
- Inserisci sempre la maiuscola a inizio frase.
- Utilizza elenchi puntati o numerati quando utile.
- Le tabelle devono essere ottimizzate per viewport mobile (leggibili da smartphone).
- Evidenzia con **strong** le entità chiave.
- Evita testo di riempimento: ogni paragrafo deve aggiungere valore informativo.
- Non usare mai la formula "la keyword" o "questa keyword".
- Evita paragrafi schematici: il testo deve essere discorsivo e ricco.
- Inserisci quando opportuno timeline, contesto storico, profili dei soggetti coinvolti, errori investigativi, rilievo processuale e impatto sociale o mediatico.
- In apertura di sezioni importanti, privilegia sintesi concise e citabili anche in ottica GEO.
- Le secondary keywords servono solo ad arricchire il contesto semantico e informativo del contenuto. Non trattarle come vincoli rigidi e non usarle per dedurre logiche di scraping.

Usa i competitor, le PAA e i documenti allegati come base informativa. Se i materiali non supportano un dettaglio, non inventarlo.

INDICAZIONI EDITORIALI AGGIUNTIVE:
{custom_prompt_block if custom_prompt_block else "Nessuna indicazione aggiuntiva: segui le istruzioni editoriali di default."}

PAA INSIGHTS:
{paa_block}

DOCUMENTI AGGIUNTIVI:
{uploaded_documents_block}

COMPETITOR DATA:
{merged}

Formato output:

TITLE TAG:
...

META DESCRIPTION:
...

EXCERPT:
...

FAQ HTML:
...

ARTICLE HTML:
...
"""

    response = client.chat.completions.create(
        model="gpt-5.4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7
    )

    content = response.choices[0].message.content or ""
    return parse_generated_content(content)


# ======================
# TXT EXPORT
# ======================

def create_txt_file(title_tag: str, meta_description: str, excerpt: str, faq: str, article: str):
    content = f"""TITLE TAG:
{title_tag}

META DESCRIPTION:
{meta_description}

EXCERPT:
{excerpt}

FAQ HTML:
{faq}

ARTICLE HTML:
{article}
"""
    buffer = BytesIO()
    buffer.write(content.encode("utf-8"))
    buffer.seek(0)

    return buffer


# ======================
# SIDEBAR API
# ======================

st.sidebar.title("API Configuration")

SERPER_KEY = get_secret("serper", "api_key")
SERPAPI_KEY = get_secret("serpapi", "api_key")
OPENAI_KEY = get_secret("openai", "api_key")

st.sidebar.caption("Le API key vengono lette dai Secrets di Streamlit.")
st.sidebar.write("Serper:", "configurato" if SERPER_KEY else "mancante")
st.sidebar.write("SerpAPI:", "configurato" if SERPAPI_KEY else "mancante")
st.sidebar.write("OpenAI:", "configurato" if OPENAI_KEY else "mancante")
st.sidebar.write(
    "WordPress:",
    "configurato" if all([
        get_secret("wordpress", "url"),
        get_secret("wordpress", "username"),
        get_secret("wordpress", "application_password"),
    ]) else "mancante"
)


# ======================
# UI
# ======================

st.markdown(
    f"""
    <div style="text-align:center; padding-top:10px;">
        <h1 style="margin-top:15px; margin-bottom:5px;">True Crime SEO &amp; GEO Writer</h1>
        <p style="font-size:18px; color:#6b7280; margin-bottom:25px;">
        Genera contenuti true crime da scraping, PAA e documenti di supporto.
        </p>
        <hr style="margin-top:10px; margin-bottom:25px;">
    </div>
    """,
    unsafe_allow_html=True
)

keyword = st.text_input("Keyword")
article_title = st.text_input("Titolo articolo (H1)")
secondary_keywords = st.text_area(
    "Secondary keywords (opzionale)",
    placeholder="Es. seo locale, ottimizzazione google business profile, recensioni online"
)
custom_prompt = st.text_area(
    "Custom prompt (opzionale)",
    placeholder="Aggiungi istruzioni editoriali extra da integrare al prompt true crime di default"
)
uploaded_files = st.file_uploader(
    "PDF/Word di supporto (opzionale)",
    type=["pdf", "doc", "docx"],
    accept_multiple_files=True
)
narrative_structure = st.selectbox(
    "Struttura narrativa",
    list(NARRATIVE_STRUCTURES.keys()),
    index=0
)
num_results = st.slider("Numero competitor organici da analizzare", 1, 20, 5)
country = st.text_input("Country code", "it")
language = st.text_input("Language code", "it")

generate = st.button("Genera contenuto")


# ======================
# GENERAZIONE
# ======================

if generate:
    if not SERPER_KEY or not SERPAPI_KEY or not OPENAI_KEY:
        st.error("Inserisci tutte le API key nella sidebar.")
        st.stop()

    if not keyword.strip():
        st.error("Inserisci una keyword.")
        st.stop()

    if not article_title.strip():
        st.error("Inserisci il titolo dell'articolo.")
        st.stop()

    st.session_state.article = ""
    st.session_state.title_tag = ""
    st.session_state.meta_description = ""
    st.session_state.excerpt = ""
    st.session_state.faq = ""
    st.session_state.article_title = article_title.strip()
    st.session_state.wordpress_post_id = None
    st.session_state.wordpress_edit_url = ""
    uploaded_documents_context = build_uploaded_documents_context(uploaded_files)

    st.subheader("SERP Insights")

    paa_placeholder = st.empty()
    url_placeholder = st.empty()
    progress = st.progress(0)

    with st.spinner("Recupero risultati organici e People Also Ask..."):
        try:
            competitors = get_competitors(
                keyword=keyword,
                num_results=num_results,
                serper_key=SERPER_KEY,
                hl=language,
                gl=country
            )

            paa = get_people_also_ask(
                keyword=keyword,
                serpapi_key=SERPAPI_KEY,
                hl=language,
                gl=country
            )
        except RuntimeError as exc:
            st.error(str(exc))
            st.stop()

    if not competitors:
        st.error("Nessun risultato organico trovato.")
        st.stop()

    with paa_placeholder.container():
        st.markdown("### People Also Ask")
        if paa:
            for q in paa:
                st.write("-", q)
        else:
            st.caption("Nessuna PAA trovata.")

    enriched = []
    scraped = []

    for i, comp in enumerate(competitors, start=1):
        scraped.append(comp["link"])

        with url_placeholder.container():
            st.markdown("### URL scrapate")
            for u in scraped:
                st.write("-", u)

        html, text = fetch_page(comp["link"])
        html_title, h1, meta_desc = extract_metadata(html)

        enriched.append({
            **comp,
            "html_title": html_title,
            "h1": h1,
            "meta_desc": meta_desc,
            "text": text
        })

        progress.progress(i / len(competitors))

    with st.spinner(f"Generazione articolo su {len(enriched)} contenuti organici..."):
        title_tag, meta_description, excerpt, faq, article = generate_article(
            keyword=keyword,
            article_title=article_title,
            competitors=enriched,
            paa=paa,
            openai_key=OPENAI_KEY,
            language=language,
            narrative_structure=narrative_structure,
            secondary_keywords=secondary_keywords,
            custom_prompt=custom_prompt,
            uploaded_documents_context=uploaded_documents_context
        )

    st.session_state.title_tag = title_tag
    st.session_state.meta_description = meta_description
    st.session_state.excerpt = excerpt
    st.session_state.faq = faq
    st.session_state.article = article


# ======================
# OUTPUT
# ======================

if st.session_state.article:
    st.subheader("Meta Data")

    st.write("**Title Tag**")
    st.write(st.session_state.title_tag)

    st.write("**Meta Description**")
    st.write(st.session_state.meta_description)

    st.write("**Excerpt**")
    st.write(st.session_state.excerpt)

    st.subheader("FAQ")
    st.code(st.session_state.faq, language="html")

    st.subheader("Articolo HTML")
    st.code(st.session_state.article, language="html")

    txt_file = create_txt_file(
        st.session_state.title_tag,
        st.session_state.meta_description,
        st.session_state.excerpt,
        st.session_state.faq,
        st.session_state.article
    )

    st.download_button(
        label="Scarica TXT",
        data=txt_file,
        file_name=f"{article_title.strip()}.txt",
        mime="text/plain"
    )

    st.subheader("WordPress")
    st.caption(
        "Il titolo viene salvato come titolo/H1 WordPress; articolo e FAQ nel corpo; "
        "l'excerpt nel campo Riassunto. Lo stato resta sempre Bozza."
    )

    if st.session_state.wordpress_post_id:
        st.success(
            f"Bozza WordPress già creata (ID {st.session_state.wordpress_post_id})."
        )
        if st.session_state.wordpress_edit_url:
            st.link_button(
                "Apri la bozza in WordPress",
                st.session_state.wordpress_edit_url
            )
    elif st.button("Invia come bozza a WordPress", type="primary"):
        if not st.session_state.article_title:
            st.error("Titolo H1 mancante: rigenera l'articolo prima dell'invio.")
        else:
            with st.spinner("Creazione della bozza WordPress..."):
                try:
                    wp_post = create_wordpress_draft(
                        title=st.session_state.article_title,
                        article_html=st.session_state.article,
                        excerpt=st.session_state.excerpt,
                        faq_html=st.session_state.faq,
                    )
                except RuntimeError as exc:
                    st.error(str(exc))
                else:
                    st.session_state.wordpress_post_id = wp_post["id"]
                    st.session_state.wordpress_edit_url = wp_post["edit_url"]
                    st.success(
                        f"Bozza WordPress creata (ID {wp_post['id']})."
                    )
                    st.link_button(
                        "Apri la bozza in WordPress",
                        wp_post["edit_url"]
                    )
