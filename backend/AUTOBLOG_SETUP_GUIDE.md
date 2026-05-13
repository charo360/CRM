# Zilo Autoblogging — Step-by-Step Setup Guide

**Status:** ✅ Backend code complete | ⏳ Infrastructure setup needed

---

## ✅ COMPLETED: Backend Implementation

The following files have been created and integrated:
- `blog/blog_service.py` — WordPress API integration
- `blog/topic_generator.py` — AI topic generation from WhatsApp chats
- `blog/post_generator.py` — Claude-powered blog post generation
- `blog/blog_scheduler.py` — Daily publishing scheduler (9 AM EAT)
- `blog/routes.py` — FastAPI endpoints at `/api/blog/*`
- Routes registered in `server.py`
- Scheduler starts automatically with server
- `python-slugify` dependency installed

---

## STEP 3: Purchase Hostinger VPS (15 minutes)

### What you need:
- Budget: $7/month for VPS KVM 2
- Credit card or PayPal

### Actions:
1. Go to **https://hostinger.com/vps-hosting**
2. Select **VPS KVM 2** plan ($6.99/month)
   - 2 CPU cores
   - 4 GB RAM
   - 80 GB NVMe storage
3. Choose **Ubuntu 22.04 LTS** as operating system
4. Select **Frankfurt** datacenter (fastest for Kenya)
5. Complete purchase
6. **SAVE** the following from confirmation email:
   - Server IP address: `___________________`
   - Root password: `___________________`
   - SSH access details

### Verify:
```bash
# Test SSH connection (replace with your IP)
ssh root@YOUR_SERVER_IP
```

**✋ STOP HERE** — Wait for VPS to be provisioned (usually 5-10 minutes)

---

## STEP 4: Install WordPress Multisite (30 minutes)

### 4.1 Connect to Server

```bash
ssh root@YOUR_SERVER_IP
# Enter the root password from email
```

### 4.2 Update System & Install LAMP Stack

Copy-paste this entire block:

```bash
# Update packages
apt update && apt upgrade -y

# Install Apache, MySQL, PHP 8.1
apt install -y apache2 mysql-server php8.1 php8.1-mysql \
  php8.1-curl php8.1-gd php8.1-mbstring php8.1-xml \
  php8.1-zip php8.1-intl php8.1-bcmath unzip wget curl

# Enable Apache modules
a2enmod rewrite ssl headers

# Restart Apache
systemctl restart apache2
```

**Verify:** Visit `http://YOUR_SERVER_IP` in browser → should see Apache default page

### 4.3 Secure MySQL & Create Database

```bash
# Run MySQL secure installation
mysql_secure_installation
```

**Answer the prompts:**
- Set root password? **Y** → Enter a strong password (SAVE IT!)
- Remove anonymous users? **Y**
- Disallow root login remotely? **Y**
- Remove test database? **Y**
- Reload privilege tables? **Y**

**Create WordPress database:**

```bash
mysql -u root -p
# Enter the MySQL root password you just set
```

Then run these SQL commands:

```sql
CREATE DATABASE zilo_wp CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'zilowp'@'localhost' IDENTIFIED BY 'CHANGE_THIS_PASSWORD_123!';
GRANT ALL PRIVILEGES ON zilo_wp.* TO 'zilowp'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

**✋ SAVE THESE CREDENTIALS:**
- Database name: `zilo_wp`
- Database user: `zilowp`
- Database password: `___________________`

### 4.4 Download & Install WordPress

```bash
# Download WordPress
cd /var/www/html
wget https://wordpress.org/latest.tar.gz
tar -xzf latest.tar.gz
mv wordpress zilo
rm latest.tar.gz

# Set permissions
chown -R www-data:www-data /var/www/html/zilo
chmod -R 755 /var/www/html/zilo

# Create uploads directory
mkdir -p /var/www/html/zilo/wp-content/uploads
chown -R www-data:www-data /var/www/html/zilo/wp-content/uploads
```

### 4.5 Configure Apache Virtual Host

```bash
nano /etc/apache2/sites-available/zilo.conf
```

**Paste this configuration:**

```apache
<VirtualHost *:80>
    ServerName zilo.pro
    ServerAlias *.zilo.pro
    DocumentRoot /var/www/html/zilo

    <Directory /var/www/html/zilo>
        Options FollowSymLinks
        AllowOverride All
        Require all granted
    </Directory>

    ErrorLog ${APACHE_LOG_DIR}/zilo_error.log
    CustomLog ${APACHE_LOG_DIR}/zilo_access.log combined
</VirtualHost>
```

**Save:** Press `Ctrl+X`, then `Y`, then `Enter`

**Enable the site:**

```bash
a2ensite zilo.conf
a2dissite 000-default.conf
systemctl restart apache2
```

### 4.6 Complete WordPress Installation

1. Visit `http://YOUR_SERVER_IP` in browser
2. Click **Let's go!**
3. Enter database details:
   - Database Name: `zilo_wp`
   - Username: `zilowp`
   - Password: (the one you set in 4.3)
   - Database Host: `localhost`
   - Table Prefix: `wp_`
4. Click **Submit** → **Run the installation**
5. Fill in site information:
   - Site Title: `Zilo Blog Network`
   - Username: `ziloadmin`
   - Password: (generate strong password — **SAVE IT!**)
   - Email: `your@email.com`
6. Click **Install WordPress**

**✋ SAVE THESE CREDENTIALS:**
- WP Admin Username: `ziloadmin`
- WP Admin Password: `___________________`

---

## STEP 5: Enable WordPress Multisite (15 minutes)

### 5.1 Enable Multisite in wp-config.php

```bash
nano /var/www/html/zilo/wp-config.php
```

**Find this line:**
```php
/* That's all, stop editing! Happy publishing. */
```

**Add BEFORE that line:**

```php
/* Multisite Configuration */
define('WP_ALLOW_MULTISITE', true);
define('MULTISITE', true);
define('SUBDOMAIN_INSTALL', true);
define('DOMAIN_CURRENT_SITE', 'zilo.pro');
define('PATH_CURRENT_SITE', '/');
define('SITE_ID_CURRENT_SITE', 1);
define('BLOG_ID_CURRENT_SITE', 1);
define('WP_DEBUG', false);
define('WP_MEMORY_LIMIT', '256M');

/* JWT Authentication */
define('JWT_AUTH_SECRET_KEY', 'GENERATE_RANDOM_64_CHAR_STRING_HERE');
define('JWT_AUTH_CORS_ENABLE', true);
```

**Save:** `Ctrl+X`, `Y`, `Enter`

**Generate JWT secret:**
```bash
openssl rand -base64 64
# Copy the output and replace GENERATE_RANDOM_64_CHAR_STRING_HERE above
```

### 5.2 Update .htaccess

```bash
nano /var/www/html/zilo/.htaccess
```

**Replace entire content with:**

```apache
RewriteEngine On
RewriteBase /
RewriteRule ^index\.php$ - [L]

# add a trailing slash to /wp-admin
RewriteRule ^wp-admin$ wp-admin/ [R=301,L]

RewriteCond %{REQUEST_FILENAME} -f [OR]
RewriteCond %{REQUEST_FILENAME} -d
RewriteRule ^ - [L]
RewriteRule ^(wp-(content|admin|includes).*) $1 [L]
RewriteRule ^(.*\.php)$ $1 [L]
RewriteRule . index.php [L]
```

**Save:** `Ctrl+X`, `Y`, `Enter`

### 5.3 Verify Multisite

1. Visit `http://YOUR_SERVER_IP/wp-admin`
2. Login with `ziloadmin` credentials
3. You should see **My Sites** in the top admin bar
4. Go to **My Sites → Network Admin → Sites**

**✅ Success:** You should see the network dashboard

---

## STEP 6: Install Required Plugins (10 minutes)

### 6.1 Install WP-CLI (command-line tool)

```bash
curl -O https://raw.githubusercontent.com/wp-cli/builds/gh-pages/phar/wp-cli.phar
chmod +x wp-cli.phar
mv wp-cli.phar /usr/local/bin/wp
```

**Verify:**
```bash
wp --info --allow-root
```

### 6.2 Install & Network-Activate Plugins

```bash
cd /var/www/html/zilo

# JWT Authentication
wp plugin install jwt-authentication-for-wp-rest-api --activate-network --allow-root

# WP Super Cache
wp plugin install wp-super-cache --activate-network --allow-root

# Yoast SEO
wp plugin install wordpress-seo --activate-network --allow-root

# Astra Theme
wp theme install astra --activate-network --allow-root
```

### 6.3 Create Application Password for API Access

1. Go to **Users → Profile** (as ziloadmin)
2. Scroll to **Application Passwords**
3. Application Name: `Zilo API`
4. Click **Add New Application Password**
5. **COPY THE PASSWORD** (format: `xxxx xxxx xxxx xxxx xxxx xxxx`)

**✋ SAVE THIS:**
- WP Application Password: `___________________`

---

## STEP 7: Create Industry Themes (20 minutes)

Create child themes for different business types:

```bash
cd /var/www/html/zilo/wp-content/themes

# Salon theme
mkdir zilo-salon
cat > zilo-salon/style.css << 'EOF'
/*
 Theme Name: Zilo Salon
 Template: astra
*/
:root {
    --ast-global-color-0: #E91E8C;
}
EOF

# Restaurant theme
mkdir zilo-restaurant
cat > zilo-restaurant/style.css << 'EOF'
/*
 Theme Name: Zilo Restaurant
 Template: astra
*/
:root {
    --ast-global-color-0: #FF6B35;
}
EOF

# Retail theme
mkdir zilo-retail
cat > zilo-retail/style.css << 'EOF'
/*
 Theme Name: Zilo Retail
 Template: astra
*/
:root {
    --ast-global-color-0: #4ECDC4;
}
EOF

# Services theme
mkdir zilo-services
cat > zilo-services/style.css << 'EOF'
/*
 Theme Name: Zilo Services
 Template: astra
*/
:root {
    --ast-global-color-0: #1A535C;
}
EOF

# Default theme
mkdir zilo-default
cat > zilo-default/style.css << 'EOF'
/*
 Theme Name: Zilo Default
 Template: astra
*/
:root {
    --ast-global-color-0: #0066CC;
}
EOF

# Set permissions
chown -R www-data:www-data /var/www/html/zilo/wp-content/themes
```

---

## STEP 8: DNS & SSL Setup (30 minutes)

### 8.1 Configure DNS (in your domain registrar)

Add these records for `zilo.pro`:

| Type  | Name | Value              | TTL  |
|-------|------|--------------------|------|
| A     | @    | YOUR_SERVER_IP     | 3600 |
| A     | *    | YOUR_SERVER_IP     | 3600 |
| CNAME | www  | zilo.pro           | 3600 |

**⏳ Wait 10-15 minutes** for DNS propagation

**Verify:**
```bash
ping zilo.pro
ping test.zilo.pro
# Both should resolve to YOUR_SERVER_IP
```

### 8.2 Install SSL Certificate (Let's Encrypt)

```bash
# Install Certbot
apt install certbot python3-certbot-apache -y

# Get wildcard SSL
certbot certonly --manual \
  --preferred-challenges dns \
  -d zilo.pro \
  -d *.zilo.pro
```

**Certbot will ask you to add a TXT record:**
1. Copy the TXT value shown
2. Add to your DNS:
   - Type: `TXT`
   - Name: `_acme-challenge`
   - Value: (paste the value)
3. Wait 2 minutes
4. Press `Enter` in terminal

### 8.3 Configure Apache SSL

```bash
nano /etc/apache2/sites-available/zilo-ssl.conf
```

**Paste:**

```apache
<VirtualHost *:443>
    ServerName zilo.pro
    ServerAlias *.zilo.pro
    DocumentRoot /var/www/html/zilo

    SSLEngine on
    SSLCertificateFile /etc/letsencrypt/live/zilo.pro/fullchain.pem
    SSLCertificateKeyFile /etc/letsencrypt/live/zilo.pro/privkey.pem

    SetEnvIf Authorization "(.*)" HTTP_AUTHORIZATION=$1

    <Directory /var/www/html/zilo>
        Options FollowSymLinks
        AllowOverride All
        Require all granted
    </Directory>

    ErrorLog ${APACHE_LOG_DIR}/zilo_ssl_error.log
    CustomLog ${APACHE_LOG_DIR}/zilo_ssl_access.log combined
</VirtualHost>
```

**Enable SSL:**

```bash
a2ensite zilo-ssl.conf
a2enmod ssl
systemctl restart apache2
```

**Setup auto-renewal:**

```bash
echo "0 12 * * * /usr/bin/certbot renew --quiet" | crontab -
```

**✅ Verify:** Visit `https://zilo.pro` → should load WordPress with SSL

---

## STEP 9: Update Backend .env (5 minutes)

On your **Render/local backend**, add to `.env`:

```dotenv
# WordPress Multisite
WP_BASE_URL=https://zilo.pro
WP_ADMIN_USER=ziloadmin
WP_ADMIN_APP_PASSWORD=xxxx xxxx xxxx xxxx xxxx xxxx
WP_JWT_SECRET=your-64-char-jwt-secret-from-wp-config
```

**Restart your backend:**
```bash
# If running locally:
# Ctrl+C then restart uvicorn

# If on Render:
# Trigger a redeploy or restart the service
```

---

## STEP 10: Test the Integration (10 minutes)

### Test 1: Create a blog via API

```bash
curl -X POST https://your-backend.onrender.com/api/blog/create \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{
    "client_id": "test123",
    "business_name": "Test Salon",
    "client_email": "test@example.com",
    "industry": "salon",
    "location": "Nairobi"
  }'
```

**Expected response:**
```json
{
  "blog_url": "https://test-salon.zilo.pro",
  "status": "created"
}
```

### Test 2: Verify subsite exists

Visit `https://test-salon.zilo.pro` → should load WordPress site

### Test 3: Manually publish a post

```bash
curl -X POST https://your-backend.onrender.com/api/blog/publish-now \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{
    "client_id": "test123"
  }'
```

**Expected:** Post should appear at `https://test-salon.zilo.pro`

---

## STEP 11: Frontend Integration (Next Phase)

See `FRONTEND_INTEGRATION.md` for React Native/Expo implementation.

---

## Troubleshooting

### Issue: "Failed to create subsite"
- Check WP-CLI is installed: `wp --info --allow-root`
- Verify permissions: `ls -la /var/www/html/zilo`

### Issue: "401 Unauthorized" when publishing
- Verify Application Password in WordPress
- Check `WP_ADMIN_APP_PASSWORD` in `.env` (must include spaces)

### Issue: Subsite returns 404
- Check Apache config: `apache2ctl -S`
- Verify DNS wildcard: `ping random.zilo.pro`
- Check .htaccess: `cat /var/www/html/zilo/.htaccess`

### Issue: SSL not working
- Renew certificate: `certbot renew --force-renewal`
- Check Apache SSL module: `a2enmod ssl && systemctl restart apache2`

---

## Summary Checklist

- [ ] Hostinger VPS purchased & accessible via SSH
- [ ] LAMP stack installed (Apache, MySQL, PHP 8.1)
- [ ] WordPress installed at `/var/www/html/zilo`
- [ ] Multisite enabled with subdomain install
- [ ] Plugins installed (JWT Auth, WP Super Cache, Yoast SEO)
- [ ] Industry child themes created (5 themes)
- [ ] DNS configured (A records + wildcard)
- [ ] SSL certificate installed (wildcard for *.zilo.pro)
- [ ] Application Password created in WordPress
- [ ] Backend `.env` updated with WP credentials
- [ ] Backend restarted/redeployed
- [ ] Test blog created successfully
- [ ] Test post published successfully

**Next:** Frontend integration → Blog activation UI in Zilo mobile app
