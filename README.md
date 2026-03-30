# Fitora Training - Backend API

Backend per l'app Fitora Training.

## Deploy su Railway (Consigliato)

### 1. Crea account Railway
1. Vai su https://railway.app
2. Registrati con GitHub

### 2. Crea progetto
1. Clicca "New Project"
2. Seleziona "Deploy from GitHub repo" oppure "Empty Project"

### 3. Aggiungi MongoDB
1. Nel progetto, clicca "New" → "Database" → "Add MongoDB"
2. Railway creerà automaticamente un database MongoDB
3. Copia la variabile `MONGO_URL` che verrà generata

### 4. Deploy del Backend
1. Clicca "New" → "GitHub Repo" oppure carica i file manualmente
2. Seleziona questa cartella come source

### 5. Configura Variabili d'Ambiente
Vai su "Variables" e aggiungi:
```
MONGO_URL=mongodb://... (copiata da Railway MongoDB)
PORT=8080
```

### 6. Ottieni URL
Dopo il deploy, vai su "Settings" → "Networking" → "Generate Domain"
L'URL sarà tipo: `https://fitora-backend-production.up.railway.app`

---

## Deploy su Render (Alternativa)

### 1. Crea account Render
1. Vai su https://render.com
2. Registrati

### 2. Crea MongoDB su MongoDB Atlas (Gratuito)
1. Vai su https://cloud.mongodb.com
2. Crea cluster gratuito (M0)
3. Crea utente database
4. Aggiungi IP 0.0.0.0/0 alla whitelist
5. Copia la connection string

### 3. Deploy Backend
1. Su Render, clicca "New" → "Web Service"
2. Connetti GitHub o carica codice
3. Configura:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn server:app --host 0.0.0.0 --port $PORT`

### 4. Variabili d'Ambiente
```
MONGO_URL=mongodb+srv://...
```

---

## File Inclusi

- `server.py` - API FastAPI principale
- `gym_exercises_database.py` - Database esercizi palestra
- `requirements.txt` - Dipendenze Python
- `Procfile` - Configurazione per Heroku/Railway
- `pyproject.toml` - Configurazione progetto

## Endpoint Principali

- `POST /api/auth/signup` - Registrazione
- `POST /api/auth/login` - Login
- `GET /api/workouts/today` - Workout del giorno
- `POST /api/workouts/{id}/complete` - Completa workout
- `GET /api/subscriptions/plans` - Piani abbonamento

## Test Locale

```bash
pip install -r requirements.txt
MONGO_URL=mongodb://localhost:27017/fitora uvicorn server:app --reload
```

## Dopo il Deploy

Una volta ottenuto l'URL (es. `https://fitora-backend.railway.app`), comunicamelo e genererò la build .aab finale con l'URL corretto.
