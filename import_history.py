import sqlite3
import psycopg2
import psycopg2.extras
import os
from dotenv import load_dotenv

load_dotenv()

# L'URL de ta base PostgreSQL sur Render
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("Erreur : DATABASE_URL n'est pas définie.")
    exit()

# Connexion SQLite (historique local)
sqlite_conn = sqlite3.connect("backtest/history.db")
sqlite_conn.row_factory = sqlite3.Row
sqlite_cursor = sqlite_conn.cursor()

# Connexion PostgreSQL (Render)
pg_conn = psycopg2.connect(DATABASE_URL)
pg_cursor = pg_conn.cursor()

# On récupère les matchs de SQLite
sqlite_cursor.execute("SELECT * FROM historical_matches")
rows = sqlite_cursor.fetchall()

print(f"Importation de {len(rows)} matchs vers PostgreSQL...")

inserted = 0
for r in rows:
    try:
        # On insère dans la table matches avec le statut FINISHED
        pg_cursor.execute("""
            INSERT INTO matches 
            (id, league, country, home, away, home_goals, away_goals, kickoff, status, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'FINISHED', NOW())
            ON CONFLICT (id) DO NOTHING
        """, (
            r["id"], r["league_name"], "International", 
            r["home"], r["away"], 
            r["home_goals"], r["away_goals"], r["kickoff"]
        ))
        inserted += 1
    except Exception as e:
        print(f"Erreur sur le match {r['id']}: {e}")
        pg_conn.rollback()

pg_conn.commit()
print(f"✅ {inserted} matchs importés avec succès !")

pg_cursor.close()
pg_conn.close()
sqlite_conn.close()
