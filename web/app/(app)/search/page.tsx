import { SearchPage } from "@/components/search/search-page";

export default async function Search({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const { q } = await searchParams;
  return <SearchPage initialQuery={q} />;
}
