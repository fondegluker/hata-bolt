from app import db


def list_sources():
    return db.query("SELECT * FROM sources ORDER BY object_type")


def houses_geo(object_type=None, region=None, sale_method=None):
    sql = """
        SELECT h.id, h.object_type, h.title, h.region, h.district, h.locality,
               h.address, h.latitude, h.longitude, h.price, h.sale_method,
               s.marker_color,
               (SELECT url FROM photos p WHERE p.house_id = h.id
                  ORDER BY p.ordr ASC LIMIT 1) AS thumb_url
        FROM houses h JOIN sources s ON s.object_type = h.object_type
        WHERE h.latitude IS NOT NULL AND h.longitude IS NOT NULL
    """
    args = []
    if object_type:
        sql += " AND h.object_type = %s"
        args.append(object_type)
    if region:
        sql += " AND h.region = %s"
        args.append(region)
    if sale_method:
        sql += " AND h.sale_method = %s"
        args.append(sale_method)
    return db.query(sql, args)


def get_house(house_id):
    h = db.query("SELECT * FROM houses WHERE id = %s", (house_id,), fetch="one")
    if not h:
        return None
    photos = db.query(
        "SELECT id, url, local_path, width, height FROM photos WHERE house_id = %s ORDER BY ordr",
        (house_id,),
    )
    h["photos"] = photos
    return h


def regions():
    return db.query(
        "SELECT region, COUNT(*) AS cnt FROM houses WHERE region IS NOT NULL GROUP BY region ORDER BY region"
    )


def stats():
    row = db.query(
        "SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE latitude IS NOT NULL) AS geo FROM houses",
        fetch="one",
    )
    by_type = db.query(
        "SELECT s.object_type, s.label, s.marker_color, COUNT(h.id) AS cnt "
        "FROM sources s LEFT JOIN houses h ON h.object_type = s.object_type "
        "GROUP BY s.object_type, s.label, s.marker_color ORDER BY s.object_type"
    )
    by_method = db.query(
        "SELECT sale_method, COUNT(*) AS cnt FROM houses GROUP BY sale_method ORDER BY cnt DESC"
    )
    photos = db.query("SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE downloaded) AS done FROM photos", fetch="one")
    last = db.query("SELECT * FROM parse_runs ORDER BY started_at DESC LIMIT 8")
    return {
        "houses": row["total"] if row else 0,
        "geocoded": row["geo"] if row else 0,
        "by_type": by_type,
        "by_method": by_method,
        "photos": photos["total"] if photos else 0,
        "photos_done": photos["done"] if photos else 0,
        "recent_runs": last,
    }


def delete_house(house_id):
    db.query("DELETE FROM houses WHERE id = %s", (house_id,), fetch="count")
