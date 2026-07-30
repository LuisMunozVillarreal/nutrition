import type { DefaultSession } from "next-auth";
import "next-auth";

type BackendSessionError = "BackendReauthenticationRequired";

interface StaffCapability {
    isStaff: boolean;
}

interface OptionalStaffCapability {
    isStaff?: boolean;
}

declare module "next-auth" {
    /**
     * Returned by `useSession`, `getSession` and received as a prop on the `SessionProvider` React Context
     */
    interface Session {
        accessToken?: string;
        error?: BackendSessionError;
        user: DefaultSession["user"] & StaffCapability;
    }

    interface User extends StaffCapability {
        accessToken?: string;
    }
}

declare module "next-auth/jwt" {
    interface JWT extends OptionalStaffCapability {
        accessToken?: string;
        error?: BackendSessionError;
        staffCapabilityRefreshedAt?: number;
    }
}
