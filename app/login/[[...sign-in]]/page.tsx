import { SignIn } from "@clerk/nextjs";

export default function LoginPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <div className="glass rounded-2xl p-1">
        <SignIn
          appearance={{
            elements: {
              rootBox: "bg-transparent",
              card: "bg-transparent shadow-none border-0",
              headerTitle: "text-foreground",
              headerSubtitle: "text-muted-foreground",
              formFieldLabel: "text-foreground",
              formFieldInput: "bg-input border-border text-foreground",
              formButtonPrimary: "bg-primary hover:bg-primary/90",
              footerActionText: "text-muted-foreground",
              footerActionLink: "text-primary",
            },
          }}
        />
      </div>
    </div>
  );
}
