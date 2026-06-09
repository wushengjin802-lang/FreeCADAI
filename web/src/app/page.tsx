import { redirect } from "next/navigation";
import { routePath } from "@/lib/routes";

export default function HomePage() {
  redirect(routePath("/admin"));
}
