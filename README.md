# Modular Web Platform (Django)

An enterprise platform built with Django focusing on modularity, high performance, and security by design. The core provides an integrated administrative dashboard with KPIs, while each business module operates decoupled in a pluggable architecture.

---

## System Modules

| Module | Description |
|--------|-------------|
| **Prospecting** | Business qualification via Google Places API (New) with automated diagnostics (SEO, SSL, metrics). |
| **Kanban** | Visual workflow management featuring WIP limits and deadlines. |
| **SLA** | Ticket tracking governed by response and resolution time policies. |
| **Monitoring** | Remote Linux server monitoring via synchronous SSH. |
| **Backup** | Per-app data export routines and complete database snapshots. |
| **Email Marketing** | Contact list management, custom SMTP senders, and broadcast campaigns with unsubscribe tokens. |

---

## Runtime Architecture

The project is containerized for deployment via **Docker Compose**:

- **web**: Django application running on a WSGI application server (Gunicorn).
- **db**: PostgreSQL relational database.
- **redis**: In-memory cache for query acceleration and distributed session storage.
- **nginx**: Web server acting as a reverse proxy and serving static/media files directly.

---

## Local Setup Guide (Docker)

### Prerequisites
- [Docker Engine](https://docs.docker.com/engine/install/) and [Docker Compose](https://docs.docker.com/compose/) installed.

### 1. Clone the repository
```bash
git clone [https://github.com/your-user/your-repo.git](https://github.com/your-user/your-repo.git)
cd your-repo