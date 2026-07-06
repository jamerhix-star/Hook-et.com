// Supabase Configuration
const SUPABASE_URL = 'https://azzsxyiedrfybchuxxxs.supabase.co';
const SUPABASE_ANON_KEY = 'sb_publishable_o8Dw_tJJtjDn-RrXESuQTQ_s65jDfs_';

// Initialize Supabase client
const { createClient } = supabase;
const supabaseClient = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
