# astro-natal-api

FastAPI backend for natal chart calculation using Swiss Ephemeris.

## License

This project is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**.

This software uses [Swiss Ephemeris](https://www.astro.com/swisseph/) (© Astrodienst AG, Switzerland),
which is distributed under AGPL-3.0. In accordance with AGPL-3.0, the source code of this
network service is made available here.

See [LICENSE](LICENSE) and [NOTICE](NOTICE) for details.

## Requirements

- Python 3.12
- Docker & Docker Compose
- Firebase project (for authentication)
- Supabase project (database + storage)
- OpenAI API key

## Setup

**1. Clone the repository**
```bash
git clone https://github.com/helenya-art/astro-natal-api.git
cd astro-natal-api
```

**2. Configure environment**
```bash
cp backend/.env.example backend/.env
# Edit backend/.env with your credentials
```

**3. Apply database migrations**

Run the SQL files in `supabase/migrations/` in order (001, 002, …) via the Supabase SQL Editor.

**4. Start the server**
```bash
cd backend
docker compose up -d
```

The API will be available at `http://localhost:8000`.

## Components

| Component | Technology |
|-----------|-----------|
| Web framework | FastAPI |
| Natal chart calculation | Swiss Ephemeris via immanuel |
| Database | Supabase (PostgreSQL) |
| Authentication | Firebase Auth |
| AI interpretation | OpenAI API |
| Rate limiting | slowapi + Redis |

## Swiss Ephemeris

Natal chart calculations (planetary positions, houses, aspects) are performed using
[Swiss Ephemeris](https://www.astro.com/swisseph/) via the
[immanuel](https://github.com/theriftlab/immanuel-python) Python library (version 1.5.3),
which uses pyswisseph 2.10.3.2.

## Source Code

Source code is available at: https://github.com/helenya-art/astro-natal-api
