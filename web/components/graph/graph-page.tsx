"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import dynamic from "next/dynamic";
import { Loader2, X, GitBranch } from "lucide-react";
import { Button } from "@/components/ui/button";

// Force graph must be client-side only (uses canvas)
const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), {
  ssr: false,
});

interface EntityNode {
  id: string;
  canonical_name: string;
  entity_type: string;
  doc_count: number;
  // Added by react-force-graph at runtime
  x?: number;
  y?: number;
}

interface RelationshipLink {
  source: string;
  target: string;
  relation_type: string;
}

interface GraphData {
  nodes: EntityNode[];
  links: RelationshipLink[];
}

interface EntityDetail {
  id: string;
  canonical_name: string;
  entity_type: string;
  aliases: string[];
  documents: { id: string; original_filename: string; role: string }[];
  facts: { field_name: string; field_value: string }[];
}

// Use Trove entity design tokens (resolved at runtime via CSS var)
// These must be hex for canvas drawing — we approximate with the token values
const TYPE_COLORS: Record<string, string> = {
  person:       "#2F6669", // --trove-entity-person
  organization: "#6B4FA0", // --trove-entity-org
  asset:        "#2D6A4F", // --trove-entity-asset
  location:     "#B8821E", // --trove-entity-place
  other:        "#6C6B62", // --trove-stone-500
};

export function GraphPage() {
  const [graphData, setGraphData] = useState<GraphData>({ nodes: [], links: [] });
  const [loading, setLoading] = useState(true);
  const [selectedEntity, setSelectedEntity] = useState<EntityDetail | null>(null);
  const [legendOpen, setLegendOpen] = useState(true);
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });

  useEffect(() => {
    const updateDimensions = () => {
      if (containerRef.current) {
        setDimensions({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight,
        });
      }
    };
    updateDimensions();
    window.addEventListener("resize", updateDimensions);
    return () => window.removeEventListener("resize", updateDimensions);
  }, []);

  const loadGraph = useCallback(async () => {
    const supabase = createClient();

    // Load entities
    const { data: entities } = await supabase
      .from("entities")
      .select("id, canonical_name, entity_type");

    if (!entities || entities.length === 0) {
      setLoading(false);
      return;
    }

    // Load document_entities to compute doc_count per entity
    const { data: docEntities } = await supabase
      .from("document_entities")
      .select("entity_id");

    const docCounts: Record<string, number> = {};
    for (const de of docEntities ?? []) {
      docCounts[de.entity_id] = (docCounts[de.entity_id] ?? 0) + 1;
    }

    // Load relationships
    const { data: relationships } = await supabase
      .from("entity_relationships")
      .select("from_entity_id, to_entity_id, relation_type");

    const nodes: EntityNode[] = entities.map((e) => ({
      id: e.id,
      canonical_name: e.canonical_name,
      entity_type: e.entity_type,
      doc_count: docCounts[e.id] ?? 0,
    }));

    const entityIds = new Set(entities.map((e) => e.id));
    const links: RelationshipLink[] = (relationships ?? [])
      .filter((r) => entityIds.has(r.from_entity_id) && entityIds.has(r.to_entity_id))
      .map((r) => ({
        source: r.from_entity_id,
        target: r.to_entity_id,
        relation_type: r.relation_type,
      }));

    setGraphData({ nodes, links });
    setLoading(false);
  }, []);

  useEffect(() => {
    loadGraph(); // eslint-disable-line react-hooks/set-state-in-effect -- initial data fetch
  }, [loadGraph]);

  const handleNodeClick = useCallback(async (node: EntityNode) => {
    const supabase = createClient();

    // Load entity details
    const { data: entity } = await supabase
      .from("entities")
      .select("id, canonical_name, entity_type, aliases")
      .eq("id", node.id)
      .single();

    // Load linked documents
    const { data: docLinks } = await supabase
      .from("document_entities")
      .select("document_id, role")
      .eq("entity_id", node.id);

    let documents: EntityDetail["documents"] = [];
    if (docLinks && docLinks.length > 0) {
      const docIds = docLinks.map((l) => l.document_id);
      const { data: docs } = await supabase
        .from("documents")
        .select("id, original_filename")
        .in("id", docIds);

      documents = docLinks.map((link) => {
        const doc = docs?.find((d) => d.id === link.document_id);
        return {
          id: link.document_id,
          original_filename: doc?.original_filename ?? "Unknown",
          role: link.role,
        };
      });
    }

    // Load current facts
    const { data: facts } = await supabase
      .from("facts")
      .select("field_name, field_value")
      .eq("entity_id", node.id)
      .is("valid_until", null)
      .order("field_name");

    setSelectedEntity({
      id: entity?.id ?? node.id,
      canonical_name: entity?.canonical_name ?? node.canonical_name,
      entity_type: entity?.entity_type ?? node.entity_type,
      aliases: Array.isArray(entity?.aliases) ? entity.aliases : [],
      documents,
      facts: facts ?? [],
    });
  }, []);

  if (loading) {
    return (
      <div
        className="flex h-full items-center justify-center"
        style={{ flexDirection: "column", gap: 12 }}
        aria-busy="true"
        aria-label="Loading knowledge graph"
      >
        <Loader2 aria-hidden="true" className="h-6 w-6 animate-spin" style={{ color: "var(--fg-muted)" }} />
        <p style={{ fontSize: 13, color: "var(--fg-muted)", fontFamily: "var(--trove-sans, sans-serif)" }}>
          Loading knowledge graph…
        </p>
      </div>
    );
  }

  if (graphData.nodes.length === 0) {
    return (
      <div
        style={{
          display: "flex",
          height: "100%",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          textAlign: "center",
          gap: 16,
        }}
      >
        <div
          style={{
            width: 72,
            height: 72,
            borderRadius: 20,
            background: "var(--accent-soft)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "var(--accent-ink)",
          }}
        >
          <GitBranch size={32} strokeWidth={1.4} />
        </div>
        <h2
          style={{
            fontFamily: "var(--trove-serif, Georgia, serif)",
            fontStyle: "italic",
            fontWeight: 400,
            fontSize: 32,
            color: "var(--fg-strong)",
            letterSpacing: "-0.015em",
          }}
        >
          No connections yet
        </h2>
        <p
          style={{
            fontFamily: "var(--trove-sans, sans-serif)",
            fontSize: 14,
            color: "var(--fg-muted)",
            maxWidth: 360,
            lineHeight: 1.6,
          }}
        >
          Upload and process documents to start building your knowledge graph.
          Entities and relationships will appear here automatically.
        </p>
      </div>
    );
  }

  return (
    <div className="relative h-full w-full" ref={containerRef}>
      <div className="absolute top-0 left-0 z-10 p-4">
        <h2 className="text-xl font-semibold">Knowledge Graph</h2>
        <p className="text-sm text-muted-foreground">
          {graphData.nodes.length} entities, {graphData.links.length} relationships
        </p>
      </div>

      {/* Collapsible legend */}
      <div style={{ position: "absolute", top: 0, right: 0, zIndex: 10, padding: 16, display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 8 }}>
        <button
          aria-label={legendOpen ? "Hide legend" : "Show legend"}
          onClick={() => setLegendOpen(!legendOpen)}
          style={{
            fontSize: 11,
            fontFamily: "var(--trove-mono, monospace)",
            color: "var(--fg-muted)",
            background: "var(--bg-elevated)",
            border: "1px solid var(--border-faint)",
            borderRadius: 6,
            padding: "3px 8px",
            cursor: "pointer",
          }}
        >
          {legendOpen ? "Hide legend" : "Legend"}
        </button>
        {legendOpen && (
          <div
            className="k-fade-in"
            style={{
              display: "flex",
              gap: 10,
              background: "var(--bg-elevated)",
              border: "1px solid var(--border-faint)",
              borderRadius: 8,
              padding: "6px 10px",
            }}
          >
            {Object.entries(TYPE_COLORS).map(([type, color]) => (
              <div key={type} style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11, fontFamily: "var(--trove-sans, sans-serif)", color: "var(--fg-muted)" }}>
                <div style={{ width: 10, height: 10, borderRadius: 999, background: color, flexShrink: 0 }} />
                <span style={{ textTransform: "capitalize" }}>{type}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <ForceGraph2D
        width={dimensions.width}
        height={dimensions.height}
        graphData={graphData}
        nodeLabel={(node) => (node as EntityNode).canonical_name}
        nodeColor={(node) => TYPE_COLORS[(node as EntityNode).entity_type] ?? TYPE_COLORS.other}
        nodeVal={(node) => Math.max(2, (node as EntityNode).doc_count * 3)}
        linkLabel={(link) => (link as unknown as RelationshipLink).relation_type.replace(/_/g, " ")}
        linkColor={() => "#d1d5db"}
        linkDirectionalArrowLength={4}
        linkDirectionalArrowRelPos={1}
        onNodeClick={(node) => handleNodeClick(node as EntityNode)}
        nodeCanvasObject={(node, ctx, globalScale) => {
          const n = node as EntityNode;
          const label = n.canonical_name;
          const fontSize = 12 / globalScale;
          ctx.font = `${fontSize}px Sans-Serif`;
          const color = TYPE_COLORS[n.entity_type] ?? TYPE_COLORS.other;
          const size = Math.max(4, (n.doc_count ?? 0) * 2 + 4);

          // Draw node circle
          ctx.beginPath();
          ctx.arc(n.x ?? 0, n.y ?? 0, size, 0, 2 * Math.PI);
          ctx.fillStyle = color;
          ctx.fill();

          // Draw label
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.fillStyle = "#E5E7EB";
          ctx.fillText(label, n.x ?? 0, (n.y ?? 0) + size + fontSize);
        }}
      />

      {/* Entity detail side panel */}
      {selectedEntity && (
        <EntitySidePanel
          entity={selectedEntity}
          onClose={() => setSelectedEntity(null)}
        />
      )}
    </div>
  );
}

function EntitySidePanel({ entity, onClose }: { entity: EntityDetail; onClose: () => void }) {
  useEffect(() => {
    const handler = (e: globalThis.KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  return (
    <div
      style={{
        position: "absolute",
        top: 0,
        right: 0,
        height: "100%",
        width: 320,
        background: "var(--bg-elevated)",
        borderLeft: "1px solid var(--border-faint)",
        boxShadow: "var(--trove-shadow-lg)",
        zIndex: 20,
        overflowY: "auto",
        animation: "k-slide-in-right 240ms var(--trove-ease-out, ease-out) both",
      }}
    >
      <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 16 }}>
        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <h3
            style={{
              fontFamily: "var(--trove-serif, Georgia, serif)",
              fontStyle: "italic",
              fontSize: 20,
              fontWeight: 400,
              color: "var(--fg-strong)",
              letterSpacing: "-0.01em",
            }}
          >
            {entity.canonical_name}
          </h3>
          <button
            aria-label="Close entity panel"
            onClick={onClose}
            onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = "var(--bg-subtle)"; }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = "none"; }}
            style={{
              width: 28, height: 28, borderRadius: 7, border: 0,
              background: "none", cursor: "pointer", display: "flex",
              alignItems: "center", justifyContent: "center",
              color: "var(--fg-muted)",
              transition: "background var(--trove-dur-fast, 140ms)",
            }}
          >
            <X aria-hidden="true" className="h-4 w-4" />
          </button>
        </div>

        {/* Entity type badge */}
        <div>
          <span
            style={{
              borderRadius: 999,
              padding: "2px 10px",
              fontSize: 11,
              fontWeight: 600,
              fontFamily: "var(--trove-mono, monospace)",
              letterSpacing: "0.06em",
              textTransform: "uppercase",
              background: `${TYPE_COLORS[entity.entity_type] ?? TYPE_COLORS.other}22`,
              color: TYPE_COLORS[entity.entity_type] ?? TYPE_COLORS.other,
            }}
          >
            {entity.entity_type}
          </span>
        </div>

        {entity.aliases.length > 0 && (
          <div>
            <p style={{ fontSize: 11, fontWeight: 600, color: "var(--fg-muted)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6, fontFamily: "var(--trove-mono, monospace)" }}>
              Aliases
            </p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {entity.aliases.map((alias, i) => (
                <span
                  key={i}
                  style={{
                    borderRadius: 6,
                    padding: "2px 8px",
                    fontSize: 12,
                    background: "var(--bg-subtle)",
                    border: "1px solid var(--border-faint)",
                    color: "var(--fg-muted)",
                    fontFamily: "var(--trove-sans, sans-serif)",
                  }}
                >
                  {alias}
                </span>
              ))}
            </div>
          </div>
        )}

        {entity.facts.length > 0 && (
          <div>
            <p style={{ fontSize: 11, fontWeight: 600, color: "var(--fg-muted)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6, fontFamily: "var(--trove-mono, monospace)" }}>
              Facts
            </p>
            <div style={{ borderRadius: 8, border: "1px solid var(--border-faint)", overflow: "hidden" }}>
              {entity.facts.map((fact, i) => (
                <div
                  key={i}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    padding: "8px 12px",
                    fontSize: 13,
                    fontFamily: "var(--trove-sans, sans-serif)",
                    borderBottom: i < entity.facts.length - 1 ? "1px solid var(--border-faint)" : "none",
                  }}
                >
                  <span style={{ color: "var(--fg-muted)" }}>{fact.field_name.replace(/_/g, " ")}</span>
                  <span style={{ color: "var(--fg-strong)", fontWeight: 500 }}>{fact.field_value}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {entity.documents.length > 0 && (
          <div>
            <p style={{ fontSize: 11, fontWeight: 600, color: "var(--fg-muted)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6, fontFamily: "var(--trove-mono, monospace)" }}>
              Documents ({entity.documents.length})
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {entity.documents.map((doc) => (
                <a
                  key={`${doc.id}-${doc.role}`}
                  href={`/document/${doc.id}`}
                  style={{
                    display: "block",
                    borderRadius: 8,
                    border: "1px solid var(--border-faint)",
                    padding: "8px 12px",
                    fontSize: 13,
                    textDecoration: "none",
                    fontFamily: "var(--trove-sans, sans-serif)",
                    transition: "background var(--trove-dur-fast, 140ms)",
                  }}
                  onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = "var(--bg-subtle)"; }}
                  onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = "transparent"; }}
                >
                  <p style={{ fontWeight: 500, color: "var(--fg)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {doc.original_filename}
                  </p>
                  <p style={{ fontSize: 11, color: "var(--fg-muted)", marginTop: 2 }}>{doc.role}</p>
                </a>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
