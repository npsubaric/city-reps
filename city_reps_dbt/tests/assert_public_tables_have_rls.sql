-- Supabase's Data API serves every table in the public schema, and the
-- website ships the key that can call it. A public table without row level
-- security could be read or changed by anyone. Returns any such table.
select schemaname, tablename
from pg_tables
where schemaname in ('public', '{{ env_var("DBT_API_SCHEMA", "public") }}')
  and not rowsecurity
