const authenticateApiKey = (req, res, next) => {
    const apiKey = req.header('X-API-Key');
    if (!apiKey || apiKey !== process.env.ML_API_KEY) {
      return res.status(401).json({ error: 'Invalid or missing API key' });
    }
    next();
}

module.exports = authenticateApiKey;