import sqlite3

def query_visual_world():
    conn = sqlite3.connect('d:/local-agent-v1/app.db')
    cursor = conn.cursor()
    cursor.execute("SELECT page_number, chunk_index, text FROM chunks WHERE text LIKE '%visual world%' OR text LIKE '%patch%' OR text LIKE '%represent%'")
    rows = cursor.fetchall()
    with open("query_results.txt", "w", encoding="utf-8") as f:
        f.write(f"Found {len(rows)} matching chunks.\n")
        for r in rows:
            f.write(f"Page {r[0]} Chunk {r[1]}:\n{r[2]}\n{'-'*40}\n")

if __name__ == '__main__':
    query_visual_world()
