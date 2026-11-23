{#
  Use a model's custom schema exactly as written, instead of dbt's default
  "<target schema>_<custom>". Only the public API table sets one (see
  models/api), so it lands in "public", where Supabase's Data API serves it.
  Everything else stays in the target schema (analytics, or ci in PR checks).
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
