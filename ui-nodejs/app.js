const express = require('express');
const bodyParser = require('body-parser');
const app = express();
const port = 3000;

// Middleware
app.use(bodyParser.urlencoded({ extended: true }));
app.use(bodyParser.json());
app.use(express.static('public'));

// Routes
app.get('/', (req, res) => {
  res.sendFile(__dirname + '/index.html');
});

app.post('/api/workspace/bootstrap', async (req, res) => {
  try {
    // Forward to controller API
    const controllerResponse = await fetch('http://localhost:8000/workspace/bootstrap', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req.body)
    });
    const result = await controllerResponse.json();
    res.json(result);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.get('/api/workspace/:workspaceId/apps', async (req, res) => {
  try {
    const controllerResponse = await fetch(`http://localhost:8000/workspace/${req.params.workspaceId}/apps`);
    const result = await controllerResponse.json();
    res.json(result);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/app/start', async (req, res) => {
  try {
    const controllerResponse = await fetch('http://localhost:8000/app/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req.body)
    });
    const result = await controllerResponse.json();
    res.json(result);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/app/stop', async (req, res) => {
  try {
    const controllerResponse = await fetch('http://localhost:8000/app/stop', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req.body)
    });
    const result = await controllerResponse.json();
    res.json(result);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.put('/api/app/sync', async (req, res) => {
  try {
    const controllerResponse = await fetch('http://localhost:8000/app/sync', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req.body)
    });
    const result = await controllerResponse.json();
    res.json(result);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.listen(port, () => {
  console.log(`UI app listening at http://localhost:${port}`);
});