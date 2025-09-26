# Security Guidelines for Cortexa Backend

## 🔒 Sensitive Content Protection

This document outlines the security measures implemented to protect sensitive content and credentials in the Cortexa backend.

## 🛡️ Implemented Security Measures

### 1. OCR Text Logging Security

**Problem**: OCR processing could log sensitive document content in plaintext logs.

**Solution**: 
- Added configurable OCR text logging via `LOG_OCR_TEXT` environment variable
- **Default**: OCR text logging is **DISABLED** (`LOG_OCR_TEXT=false`)
- Text length truncation via `OCR_TEXT_LOG_MAX_LENGTH` (default: 200 characters)
- Security warning when text is truncated: `... [TRUNCATED FOR SECURITY]`

**Environment Variables**:
```bash
# Enable OCR text logging (only for development/debugging)
LOG_OCR_TEXT=false  # Default: false for security

# Limit logged text length to prevent sensitive content exposure
OCR_TEXT_LOG_MAX_LENGTH=200  # Default: 200 characters
```

### 2. Password Security

**Problem**: Hardcoded passwords in user creation endpoints.

**Solution**:
- Replaced hardcoded `"password"` with configurable environment variable
- Added SHA-256 password hashing
- Secure fallback password with warning message

**Environment Variables**:
```bash
# Default password for development user creation
DEFAULT_USER_PASSWORD=ChangeMe123!Please  # Change in production!
```

### 3. Credential Protection

**All sensitive credentials are now environment-based**:
```bash
# Database Credentials
DB_PASSWORD=your_db_password

# Purple Fabric API Credentials
PF_API_KEY=your_pf_api_key
PF_USERNAME=your_pf_username
PF_PASSWORD=your_pf_password
OCR_ASSET_ID=your_ocr_asset_id

# AWS Credentials (if using S3)
AWS_ACCESS_KEY_ID=your_aws_access_key
AWS_SECRET_ACCESS_KEY=your_aws_secret_key
AWS_SESSION_TOKEN=your_aws_session_token
```

### 4. Logging Security

**Measures**:
- Removed debug prints that could expose sensitive information
- Fixed duplicate logging that could increase exposure surface
- Added security-aware logging with conditional text exposure
- Logger propagation disabled to prevent uncontrolled log distribution

## 🚨 Security Recommendations

### For Production Deployment

1. **Always Set These Environment Variables**:
   ```bash
   LOG_OCR_TEXT=false
   OCR_TEXT_LOG_MAX_LENGTH=50  # Very limited for production
   DEFAULT_USER_PASSWORD=SecureRandomPassword123!
   ```

2. **Use Proper Password Hashing**:
   - Current implementation uses SHA-256 for development
   - **Recommendation**: Upgrade to bcrypt or scrypt for production
   - Consider implementing proper user authentication/authorization

3. **Environment File Security**:
   - Never commit `.env` files to version control
   - Use secure secret management (AWS Secrets Manager, Azure Key Vault, etc.)
   - Rotate credentials regularly

4. **Log Management**:
   - Monitor logs for sensitive content exposure
   - Implement log rotation and secure storage
   - Consider centralized logging with security filtering

### For Development

1. **Safe Testing**:
   ```bash
   LOG_OCR_TEXT=true  # Only for debugging OCR issues
   OCR_TEXT_LOG_MAX_LENGTH=100  # Limited even in development
   ```

2. **Document Content**:
   - Use test documents without sensitive information
   - Be aware that OCR text may be logged when enabled
   - Clear logs after sensitive document testing

## 🔍 Security Audit Checklist

- [ ] All credentials moved to environment variables
- [ ] OCR text logging disabled in production
- [ ] Password hashing implemented
- [ ] Debug prints removed/secured
- [ ] Environment files excluded from version control
- [ ] Log rotation and secure storage configured
- [ ] Regular security audits scheduled

## 📞 Security Incident Response

If sensitive content is detected in logs:

1. **Immediate Actions**:
   - Set `LOG_OCR_TEXT=false`
   - Restart application to apply changes
   - Secure/rotate any exposed credentials
   - Clear/secure existing log files

2. **Investigation**:
   - Identify scope of potential exposure
   - Review log access permissions
   - Check for unauthorized access to logs

3. **Prevention**:
   - Update security configurations
   - Implement additional monitoring
   - Train team on security best practices

## 🛠️ Configuration Examples

### Secure Production Environment
```bash
# Security: Disable sensitive content logging
LOG_OCR_TEXT=false
OCR_TEXT_LOG_MAX_LENGTH=0

# Security: Strong authentication
DEFAULT_USER_PASSWORD=VerySecureRandomPassword123!@#

# All other credentials via secure secret management
```

### Development Environment
```bash
# Development: Limited OCR text logging for debugging
LOG_OCR_TEXT=true
OCR_TEXT_LOG_MAX_LENGTH=100

# Development: Still use secure password
DEFAULT_USER_PASSWORD=DevPassword123!
```

---

**Remember**: Security is an ongoing process. Regularly review and update these measures as the application evolves.
