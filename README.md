# Skaiscanner

A simple flight search project inspired by Skyscanner.

## Project Structure

- `backend/` - Django API, database models, background jobs, and search logic.
- `skyclone/` - React frontend for searching and viewing flight results.

## Basic Setup

Start the backend services from the `backend` folder:

```bash
docker compose up -d
```

Run the Django backend:

```bash
cd backend
source .venv/bin/activate
python manage.py runserver
```

Run the frontend:

```bash
cd skyclone
npm install
npm run dev
```