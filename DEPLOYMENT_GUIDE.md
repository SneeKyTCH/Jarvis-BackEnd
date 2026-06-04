# JARVIS Deployment Guide - Step by Step

## 🚀 DEPLOYMENT IN 15 MINUTES

### STEP 1: Set Up GitHub (2 minutes)

#### Option A: If you don't have jarvis-backend repo yet

```bash
# 1. Create new repo on GitHub
# Go to https://github.com/new
# Name: jarvis-backend
# Description: JARVIS AI Assistant Backend API
# Make it PUBLIC
# DON'T initialize with README (we have one)
# Click "Create repository"

# 2. Add GitHub as remote
cd C:\Users\SneeKy\Desktop\jarvis-backend
git remote add origin https://github.com/YOUR_USERNAME/jarvis-backend.git
git branch -M main
git push -u origin main
```

#### Option B: If you already have the repo

```bash
cd C:\Users\SneeKy\Desktop\jarvis-backend
git push origin main  # Push latest code
```

---

### STEP 2: Deploy Backend to Render (5 minutes)

1. Go to https://dashboard.render.com
2. Click "New +" → "Web Service"
3. Select your GitHub repo (jarvis-backend)
4. Configure:
   - **Name**: jarvis-api
   - **Environment**: Python 3.11
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn -w 4 -b 0.0.0.0:$PORT app.main:app`
5. Add Environment Variables:
   ```
   ANTHROPIC_API_KEY=sk-ant-[YOUR_KEY_HERE]
   OPENAI_API_KEY=sk-[YOUR_KEY_HERE]
   ELEVENLABS_API_KEY=[YOUR_KEY_HERE]
   ENVIRONMENT=production
   DEBUG=false
   ```
6. Click "Deploy"
7. Wait for deployment (2-3 minutes)
8. Copy your API URL: `https://jarvis-api-xxxxx.onrender.com`

---

### STEP 3: Deploy Frontend to Vercel (5 minutes)

1. Go to https://vercel.com
2. Click "New Project"
3. Select your GitHub repo (jarvis-web)
4. Configure:
   - **Framework Preset**: Next.js
   - **Root Directory**: ./
5. Add Environment Variables:
   ```
   NEXT_PUBLIC_API_URL=https://jarvis-api-xxxxx.onrender.com
   ```
   (Use the URL from STEP 2)
6. Click "Deploy"
7. Wait for deployment (1-2 minutes)
8. Get your frontend URL: `https://jarvis-web-xxxxx.vercel.app`

---

### STEP 4: Test Your Deployment (3 minutes)

1. Open your frontend URL in browser
2. Register a new account
   - Email: test@example.com
   - Username: testuser
   - Password: Test123!
3. Click Login
4. Try Web Search:
   - Click "Search the web"
   - Search for "Claude AI"
5. Should see search results!

---

## 🔑 GETTING API KEYS

### Anthropic (Claude API)
1. Go to https://console.anthropic.com
2. Sign up / Log in
3. Click "Get API Key"
4. Copy your API key (starts with `sk-ant-`)

### OpenAI (GPT-4o fallback)
1. Go to https://platform.openai.com
2. Sign up / Log in
3. Go to API Keys
4. Create new API key
5. Copy it (starts with `sk-`)

### Eleven Labs (Optional - Voice)
1. Go to https://elevenlabs.io
2. Sign up / Log in
3. Get your API key from settings
4. Copy it

---

## ✅ VERIFICATION CHECKLIST

After deployment, verify:

```bash
# Test backend health
curl https://jarvis-api-xxxxx.onrender.com/health

# Should return:
# {"status":"healthy","service":"JARVIS Backend API"}

# Test frontend loads
# Open https://jarvis-web-xxxxx.vercel.app in browser
# Should see login page
```

---

## 🎯 WHAT WORKS NOW

✅ Register new users
✅ Login with email/password
✅ View user profile
✅ Search the web (DuckDuckGo)
✅ See conversation history
✅ Multi-language interface

⏳ Coming soon (will fix):
→ Send chat messages
→ Real-time AI responses

---

## 🔧 TROUBLESHOOTING

### "Failed to connect to API"
- Check NEXT_PUBLIC_API_URL is set correctly in Vercel
- Make sure backend is deployed and running
- Check Render dashboard for errors

### "500 Internal Server Error"
- Check Render logs for errors
- Verify environment variables are set
- Try redeploying

### "Cannot register user"
- Check backend is running
- Check CORS is enabled
- Look at Render logs

---

## 📞 MONITORING

After deployment, monitor these:

**Render Dashboard:**
- https://dashboard.render.com/services
- Look for "jarvis-api" service
- Check logs for errors
- Monitor response time

**Vercel Dashboard:**
- https://vercel.com/dashboard
- Click "jarvis-web"
- Check deployment status
- View analytics

---

## 🚀 YOU'RE LIVE!

Once deployed:
- Backend: `https://jarvis-api-xxxxx.onrender.com`
- Frontend: `https://jarvis-web-xxxxx.vercel.app`
- Share with friends!

---

## 📋 NEXT STEPS (After Launch)

1. **Monitor Performance**
   - Check error rates
   - Monitor API response times
   - Track user signups

2. **Fix Chat Endpoint** (30 minutes)
   - Add query parameter support for tokens
   - OR implement custom middleware
   - Redeploy

3. **Collect Feedback**
   - What features do users want?
   - What's broken?
   - What's slow?

4. **Iterate**
   - Fix bugs
   - Add features
   - Optimize performance

---

**Good luck! Your AI assistant is live! 🎊**
