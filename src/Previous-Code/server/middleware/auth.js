const { createClient } = require("@supabase/supabase-js");

const authenticateToken = async (req, res, next) => {
  try {
    const authHeader = req.headers.authorization;
    const token = authHeader?.replace("Bearer ", "");

    if (!token) {
      return res.status(401).json({ error: "Authentication required" });
    }

    // Create per-request client with user's JWT
    // This client "acts as" the authenticated user
    const userClient = createClient(
      process.env.SUPABASE_URL,
      process.env.SUPABASE_ANON_KEY,
      {
        global: {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        },
      }
    );

    // Validate token and get user
    const {
      data: { user },
      error,
    } = await userClient.auth.getUser();

    if (error || !user) {
      return res.status(401).json({ error: "Invalid or expired token" });
    }

    // Get user's profile from profiles table (id, email, name, display_name)
    const { data: profile, error: profileError } = await userClient
      .from("profiles")
      .select("name, display_name")
      .eq("id", user.id)
      .single();

    if (profileError) {
      console.error("Profile fetch error:", profileError);
      // Profile might not exist yet, that's ok
      req.user = {
        id: user.id,
        email: user.email,
        name: null,
        display_name: null,
      };
    } else {
      // Attach user info and client to request
      req.user = {
        id: user.id,
        email: user.email,
        name: profile.name,
        display_name: profile.display_name,
      };
    }

    req.supabase = userClient; // Routes will use this client

    next();
  } catch (err) {
    console.error("Authentication error:", err);
    return res.status(500).json({ error: "Authentication failed" });
  }
};

module.exports = { authenticateToken };
