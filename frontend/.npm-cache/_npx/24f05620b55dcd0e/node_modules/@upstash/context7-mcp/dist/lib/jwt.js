import * as jose from "jose";
import { CLERK_DOMAIN } from "./constants.js";
const JWKS_URL = `https://${CLERK_DOMAIN}/.well-known/jwks.json`;
const ISSUER = `https://${CLERK_DOMAIN}`;
const jwks = jose.createRemoteJWKSet(new URL(JWKS_URL));
export function isJWT(token) {
    const parts = token.split(".");
    return parts.length === 3;
}
export async function validateJWT(token) {
    try {
        await jose.jwtVerify(token, jwks, {
            issuer: ISSUER,
        });
        return { valid: true };
    }
    catch (error) {
        if (error instanceof jose.errors.JWTExpired) {
            return { valid: false, error: "Token expired" };
        }
        if (error instanceof jose.errors.JWTClaimValidationFailed) {
            return { valid: false, error: "Invalid token claims" };
        }
        if (error instanceof jose.errors.JWSSignatureVerificationFailed) {
            return { valid: false, error: "Invalid signature" };
        }
        return { valid: false, error: "Invalid token" };
    }
}
