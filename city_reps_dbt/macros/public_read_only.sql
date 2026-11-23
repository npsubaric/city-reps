{#
  Post-hook for tables the public website reads through Supabase's Data API.

  Supabase gives its public roles (anon, authenticated) full access to new
  tables in the public schema by default. This turns that into read-only:
    - row level security on, with one policy that allows reading
      (no policy allows writing, so inserts, updates and deletes are refused)
    - only SELECT granted, as a second layer
  dbt rebuilds the table on every run, so this runs every time.
  On a plain Postgres without Supabase's roles, the grants are skipped.
#}
{% macro public_read_only(relation) %}
    alter table {{ relation }} enable row level security;
    create policy "Anyone can read" on {{ relation }} for select using (true);
    do $$ begin
        if exists (select from pg_roles where rolname = 'anon') then
            execute 'revoke all on {{ relation }} from anon, authenticated';
            execute 'grant select on {{ relation }} to anon, authenticated';
        end if;
    end $$;
{% endmacro %}
