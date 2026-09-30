-- Additive migration for the local vertical slice; no production RLS claim.
ALTER TABLE jobs ADD COLUMN gate jsonb;
ALTER TABLE jobs ADD COLUMN gate_policy jsonb;
