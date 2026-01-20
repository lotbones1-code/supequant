# 🔧 FIX PASSPHRASE ISSUE

## The Problem
Error: "OK-ACCESS-PASSPHRASE incorrect" (50105)

This means the passphrase in your `.env` file doesn't match what you set in OKX.

## ✅ Solution

### Step 1: Check Your OKX Passphrase

1. Go to OKX → API Management
2. Find your API key "muin"
3. Click "View" or "Edit"
4. Look at the passphrase field
5. Copy it EXACTLY as shown

### Step 2: Update .env File

Edit your `.env` file and update the passphrase:

```bash
OKX_PASSPHRASE=your_actual_passphrase_from_okx
```

**Important**: 
- Must match EXACTLY (case-sensitive)
- No extra spaces
- Copy it directly from OKX

### Step 3: Common Issues

**If passphrase has special characters:**
- Make sure they're copied exactly
- Check for hidden characters

**If you forgot the passphrase:**
- You'll need to create a NEW API key in OKX
- Or reset the passphrase in OKX (if possible)

### Step 4: Test

After updating, restart:
```bash
python main.py
```

## ⚠️ Most Likely Issue

The passphrase you set in OKX when creating the key is probably **different** from `Stcuk567@`.

**Check in OKX** what passphrase you actually set, then update `.env` to match it exactly.
