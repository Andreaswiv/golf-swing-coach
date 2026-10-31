import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

export default function NotFound() {
  return (
    <Card className="mx-auto max-w-md items-center p-8 text-center">
      <div>
        <h1 className="text-2xl">Page not found</h1>
        <p className="mt-2 text-muted-foreground">That address does not exist.</p>
      </div>
      <Button asChild variant="outline">
        <Link to="/">Go to your swings</Link>
      </Button>
    </Card>
  );
}
