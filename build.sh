#!/usr/bin/env bash
set -o errexit

pip install -r backend/requirements.txt
python backend/manage.py collectstatic --no-input
