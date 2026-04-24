import {
  Document,
  Link,
  Page,
  Path,
  StyleSheet,
  Svg,
  Text,
  View,
} from "@react-pdf/renderer";

import type { BriefPresentation } from "../briefPresentation";

/** Same path as `Logomark.tsx` (Arkenstone mark). */
const LOGO_PATH =
  "M830.035 682.864V341.136L512 52.2656L193.964 341.136V682.864L512 971.734L830.035 682.864ZM512 334.85L641.542 452.573V571.427L512 689.15L382.458 571.427V452.573L512 334.85ZM533.202 895.18V727.05L787.63 495.941V664.071L533.202 895.18ZM787.63 438.745L683.947 532.898V433.78L533.202 296.825V128.694L787.63 359.803V438.683V438.745ZM490.797 128.694V296.825L340.053 433.78V532.898L236.432 438.745V359.866L490.86 128.757L490.797 128.694ZM236.369 496.004L339.99 590.157L452.042 691.978L490.734 727.112V895.243L236.306 664.134V496.004H236.369Z";

const brand = {
  black: "#161616",
  bone: "#e8e4d4",
  olive800: "#2a3120",
  olive600: "#5d6946",
  orange500: "#e85d2c",
  muted: "#5d6946",
};

const styles = StyleSheet.create({
  page: {
    paddingTop: 36,
    paddingBottom: 40,
    paddingHorizontal: 44,
    fontFamily: "DM Sans",
    fontSize: 10,
    lineHeight: 1.45,
    color: brand.black,
    backgroundColor: "#ffffff",
  },
  headerRow: {
    flexDirection: "row",
    alignItems: "center",
    marginBottom: 14,
    paddingBottom: 10,
    borderBottomWidth: 1,
    borderBottomColor: brand.bone,
  },
  brandKicker: {
    marginLeft: 10,
    fontSize: 8,
    letterSpacing: 1.4,
    textTransform: "uppercase",
    color: brand.orange500,
    fontWeight: 700,
  },
  rowMeta: {
    fontSize: 8,
    color: brand.muted,
    marginBottom: 14,
  },
  title: {
    fontSize: 18,
    fontWeight: 700,
    color: brand.olive800,
    marginBottom: 6,
  },
  sub: {
    fontSize: 9,
    color: brand.muted,
    marginBottom: 10,
  },
  tagRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    marginBottom: 10,
  },
  tag: {
    fontSize: 8,
    paddingVertical: 3,
    paddingHorizontal: 8,
    borderWidth: 1,
    borderColor: "rgba(93, 105, 70, 0.35)",
    color: brand.olive600,
    marginRight: 6,
    marginBottom: 4,
  },
  tagVerdict: {
    borderColor: "rgba(22, 22, 22, 0.18)",
  },
  meta: {
    fontSize: 8,
    color: brand.muted,
  },
  why: {
    fontSize: 9,
    color: brand.muted,
    marginBottom: 8,
  },
  rationale: {
    fontSize: 10,
    marginBottom: 12,
  },
  sectionTitle: {
    fontSize: 11,
    fontWeight: 700,
    color: brand.olive800,
    marginTop: 10,
    marginBottom: 6,
  },
  dlRow: {
    marginBottom: 8,
  },
  dt: {
    fontSize: 8,
    fontWeight: 700,
    textTransform: "uppercase",
    letterSpacing: 0.6,
    color: brand.orange500,
    marginBottom: 2,
  },
  dd: {
    fontSize: 10,
  },
  notes: {
    fontSize: 9,
    color: brand.muted,
    marginTop: 2,
  },
  listItem: {
    marginBottom: 4,
    paddingLeft: 8,
  },
  hookText: {
    marginBottom: 2,
  },
  link: {
    color: "#2a6ebb",
    textDecoration: "none",
  },
});

export type BriefPdfInput = {
  rowNumber: number;
  companyQueried: string;
  domain: string | null;
  savedAt?: string;
  pres: BriefPresentation;
};

function Header() {
  return (
    <View style={styles.headerRow}>
      <Svg width={22} height={22} viewBox="0 0 1024 1024">
        <Path d={LOGO_PATH} fill={brand.olive800} />
      </Svg>
      <Text style={styles.brandKicker}>Strider · Prospect brief</Text>
    </View>
  );
}

function BriefBody({ input }: { input: BriefPdfInput }) {
  const { pres, rowNumber, companyQueried, domain, savedAt } = input;
  const sp = pres.salesPrep;

  return (
    <>
      <Text style={styles.rowMeta}>
        Row {rowNumber}
        {savedAt ? ` · Generated ${savedAt}` : ""}
      </Text>
      <Text style={styles.title}>{pres.title}</Text>
      <Text style={styles.sub}>
        Queried as {companyQueried}
        {domain ? ` · ${domain}` : ""}
      </Text>
      <View style={styles.tagRow}>
        {pres.tiersDisplay ? <Text style={styles.tag}>{pres.tiersDisplay}</Text> : null}
        {pres.postureConfidenceDisplay || pres.verdict ? (
          <Text style={[styles.tag, styles.tagVerdict]}>
            {pres.postureConfidenceDisplay ?? pres.verdict}
          </Text>
        ) : null}
        {pres.revBand ? <Text style={styles.meta}>{pres.revBand}</Text> : null}
        {pres.wallSeconds !== undefined && pres.costUsd !== undefined ? (
          <Text style={styles.meta}>
            {pres.wallSeconds.toFixed(0)}s · ${pres.costUsd.toFixed(2)}
          </Text>
        ) : null}
      </View>

      {pres.why ? (
        <Text style={styles.why}>
          <Text style={{ fontWeight: 700 }}>Why not higher confidence </Text>
          {pres.why}
        </Text>
      ) : null}
      {pres.rationale ? <Text style={styles.rationale}>{pres.rationale}</Text> : null}

      {sp ? (
        <View wrap={false}>
          <Text style={styles.sectionTitle}>Before the call</Text>
          {sp.whatTheyDo ? (
            <View style={styles.dlRow}>
              <Text style={styles.dt}>What they do</Text>
              <Text style={styles.dd}>
                {sp.whatTheyDo.summary}
                {sp.whatTheyDo.citation_url ? " " : ""}
                {sp.whatTheyDo.citation_url ? (
                  <Link src={sp.whatTheyDo.citation_url} style={styles.link}>
                    Source
                  </Link>
                ) : null}
              </Text>
            </View>
          ) : null}
          {sp.fedramp ? (
            <View style={styles.dlRow}>
              <Text style={styles.dt}>FedRAMP</Text>
              <Text style={styles.dd}>
                {sp.fedramp.status}
                {sp.fedramp.stage ? ` — ${sp.fedramp.stage}` : ""}
              </Text>
              {sp.fedramp.notes ? <Text style={styles.notes}>{sp.fedramp.notes}</Text> : null}
              {sp.fedramp.citation_url ? (
                <Link src={sp.fedramp.citation_url} style={styles.link}>
                  Source
                </Link>
              ) : null}
            </View>
          ) : null}
          {sp.hrPeo ? (
            <View style={styles.dlRow}>
              <Text style={styles.dt}>HR PEO</Text>
              <Text style={styles.dd}>
                {sp.hrPeo.status}
                {sp.hrPeo.provider_hint ? ` — ${sp.hrPeo.provider_hint}` : ""}
                {sp.hrPeo.citation_url ? " " : ""}
                {sp.hrPeo.citation_url ? (
                  <Link src={sp.hrPeo.citation_url} style={styles.link}>
                    Source
                  </Link>
                ) : null}
              </Text>
            </View>
          ) : null}
          {sp.lastFunding ? (
            <View style={styles.dlRow}>
              <Text style={styles.dt}>Last funding</Text>
              <Text style={styles.dd}>
                {[sp.lastFunding.round_label, sp.lastFunding.observed_date].filter(Boolean).join(" · ") ||
                  "—"}
                {sp.lastFunding.confidence && sp.lastFunding.confidence !== "unknown"
                  ? ` (${sp.lastFunding.confidence})`
                  : ""}
                {sp.lastFunding.citation_url ? " " : ""}
                {sp.lastFunding.citation_url ? (
                  <Link src={sp.lastFunding.citation_url} style={styles.link}>
                    Source
                  </Link>
                ) : null}
              </Text>
            </View>
          ) : null}
          {sp.federalPrimes.length > 0 ? (
            <View style={styles.dlRow}>
              <Text style={styles.dt}>Federal primes</Text>
              {sp.federalPrimes.map((row, i) => (
                <Text key={i} style={styles.listItem}>
                  <Text style={{ fontWeight: 700 }}>{row.agency_or_context}</Text>
                  {row.amount_or_band ? ` — ${row.amount_or_band}` : ""}
                  {row.period_hint ? ` (${row.period_hint})` : ""}
                  {row.citation_url ? " " : ""}
                  {row.citation_url ? (
                    <Link src={row.citation_url} style={styles.link}>
                      USAspending
                    </Link>
                  ) : null}
                </Text>
              ))}
            </View>
          ) : null}
        </View>
      ) : null}

      {pres.roles.length > 0 ? (
        <View wrap={false}>
          <Text style={styles.sectionTitle}>Target roles</Text>
          {pres.roles.map((role, i) => (
            <Text key={i} style={styles.listItem}>
              <Text style={{ fontWeight: 700 }}>{role.title ?? "—"}</Text>
              {role.rationale ? ` — ${role.rationale}` : ""}
            </Text>
          ))}
        </View>
      ) : null}

      {pres.hooks.length > 0 ? (
        <View wrap={false}>
          <Text style={styles.sectionTitle}>Hooks</Text>
          {pres.hooks.map((h, i) => (
            <View key={i} style={{ marginBottom: 8 }}>
              <Text style={[styles.dd, styles.hookText]}>{h.text ?? "—"}</Text>
              {h.citation_url ? (
                <Link src={h.citation_url} style={styles.link}>
                  Source
                </Link>
              ) : null}
            </View>
          ))}
        </View>
      ) : null}
    </>
  );
}

type Props = {
  entries: BriefPdfInput[];
};

export default function BriefPdfDocument({ entries }: Props) {
  const title =
    entries.length === 1
      ? `${entries[0].pres.title} — Prospect brief`
      : `Prospect briefs (${entries.length})`;

  return (
    <Document title={title} author="Strider" subject="Prospect research">
      {entries.map((input, i) => (
        <Page key={i} size="LETTER" wrap style={styles.page}>
          <Header />
          <BriefBody input={input} />
        </Page>
      ))}
    </Document>
  );
}
