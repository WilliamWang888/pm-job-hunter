import sqlite3, json, sys
c = sqlite3.connect('data/tracker.db')
c.row_factory = sqlite3.Row
rows = c.execute(
    "SELECT id,company,title,location,url,apply_url,substr(description,1,1800) as description "
    "FROM jobs WHERE date(last_seen_at)=date('now')"
).fetchall()
data = [dict(r) for r in rows]
for d in data:
    d['description_excerpt'] = d.pop('description') or ''
json.dump({'candidates': data, 'stats': {'to_score': len(data)}},
          open('data/candidates.json', 'w', encoding='utf-8'), indent=2)
print(len(data))
