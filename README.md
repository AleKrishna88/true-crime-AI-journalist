# True Crime AI Journalist + WordPress

Tool SEO per la creazione di contenuti true crime tramite scraping dei migliori
siti posizionati in SERP e le PAA. La versione include l'invio manuale del
risultato a WordPress come bozza.

## Secrets Streamlit

Configurare questi valori in `Manage app > Settings > Secrets`:

```toml
[wordpress]
url = "https://www.enciclopediadelmale.it"
username = "USERNAME_WORDPRESS"
application_password = "PASSWORD_APPLICATIVA"

[openai]
api_key = "OPENAI_API_KEY"

[serper]
api_key = "SERPER_API_KEY"

[serpapi]
api_key = "SERPAPI_API_KEY"
```

Le credenziali non devono essere salvate nel repository.
