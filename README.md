# auroraryan0301.github.io

Personal homepage for **Ruihan Yu (Aurora)** — M2 in Umetani Lab,
The University of Tokyo.

Built on the
[academicpages](https://github.com/academicpages/academicpages.github.io)
Jekyll template, trimmed to a minimal layout (About + Publications only)
with a `suikasibyl`-inspired typography pass (Helvetica Neue + PingFang SC
+ Google Sans for headings, `#2c3e50` text on white, `#209cee` hover links).

## Editing

- `_pages/about.md` — front-page bio.
- `_publications/*.md` — one file per paper.
- `_config.yml` — site title, author sidebar info, social links.
- `_data/navigation.yml` — top nav (currently just *Publications*).
- `_sass/_custom.scss` — visual overrides.
- `images/profile.png` — replace with your own avatar.

## Local preview

```bash
bundle install
bundle exec jekyll serve
# -> http://127.0.0.1:4000/
```

Or Docker:

```bash
docker-compose up
```

## Deploy

GitHub Pages auto-builds the `master` branch.
Push to `AuroraRyan0301/AuroraRyan0301.github.io`.
