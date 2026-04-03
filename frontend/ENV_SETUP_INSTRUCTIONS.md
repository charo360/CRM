# Environment Setup for Production

## Issue
Images (product catalog and profile pictures) are not displaying because the app doesn't know the backend URL.

## Solution
Create a `.env` file in the `frontend` directory with the following content:

```
EXPO_PUBLIC_BACKEND_URL=https://crm-1-pnfo.onrender.com
```

## Steps to Fix

1. Navigate to the frontend directory:
   ```
   cd c:\Users\sarch\Desktop\crm\crm-prod\frontend
   ```

2. Create a new file named `.env` (note: starts with a dot)

3. Add this single line to the file:
   ```
   EXPO_PUBLIC_BACKEND_URL=https://crm-1-pnfo.onrender.com
   ```

4. Save the file

5. Restart your Expo development server:
   ```
   npx expo start --clear
   ```

## What This Fixes

- **Product catalog images**: Images will now load from `https://crm-1-pnfo.onrender.com/uploads/products/...`
- **Profile pictures**: Customer profile pictures will load from your Render backend
- **All media**: Any media files served by the backend will now display correctly

## Note
The `.env` file is gitignored for security, so you'll need to create it manually on each machine/deployment.
