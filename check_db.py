from app.db.supabase import supabase
res = supabase.table('plants').select('*').limit(1).execute()
print(res.data)
