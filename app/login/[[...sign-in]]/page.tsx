import { SignInForm } from "@/components/auth/SignInForm";
import { Zap } from "lucide-react";

export default function LoginPage() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-background gap-8">
      <div className="flex items-center gap-2">
        <div className="w-8 h-8 rounded-lg bg-accent flex items-center justify-center">
          <Zap className="w-4 h-4 text-white" />
        </div>
        <span className="font-semibold text-lg">Lucid AI Trader</span>
      </div>
      <div className="glass rounded-2xl p-8">
        <SignInForm />
      </div>
    </div>
  );
}
