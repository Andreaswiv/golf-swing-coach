import type { ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";

/** A card that folds open: `header` is always shown, the content below a divider. */
export default function FoldCard({
  header,
  defaultOpen,
  contentClassName,
  children,
}: {
  header: ReactNode;
  defaultOpen?: boolean;
  contentClassName?: string;
  children: ReactNode;
}) {
  return (
    <Collapsible asChild defaultOpen={defaultOpen}>
      <Card className="group gap-0 py-0">
        <CollapsibleTrigger className="flex w-full cursor-pointer items-center justify-between gap-3 rounded-xl p-6 text-left">
          <span>{header}</span>
          <ChevronDown className="size-5 text-muted-foreground transition-transform group-data-[state=open]:rotate-180" />
        </CollapsibleTrigger>
        <CollapsibleContent className={cn("border-t p-6", contentClassName)}>{children}</CollapsibleContent>
      </Card>
    </Collapsible>
  );
}
