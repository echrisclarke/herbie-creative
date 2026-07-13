import type { Brief, Product } from './api'

/** Match backend slugify_name / product_slug closely enough for UI lookups. */
export function productSlug(name: string): string {
  const slug = (name || '')
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
  return slug || 'item'
}

export function matchBriefProduct(
  brief: Brief,
  productKey: string | undefined | null,
): Product | undefined {
  if (!productKey) return undefined
  const want = productSlug(productKey)
  return brief.products.find(
    (p) => p.name === productKey || productSlug(p.name) === want || productSlug(p.name) === productSlug(productKey),
  )
}

export function emptyProduct(name = 'New product'): Product {
  return {
    name: name.trim() || 'New product',
    category: '',
    product_mode: 'generate-concept',
    product_role: 'product_hero',
    asset_hint: '',
    input_asset_path: null,
    input_asset_paths: [],
    landing_url: null,
    notes: '',
    message: '',
    cta: '',
    supporting_copy: '',
    creative_direction: '',
    style_reference_paths: [],
    background_reference_paths: [],
  }
}

export function duplicateProduct(product: Product): Product {
  const base = product.name.trim() || 'Product'
  return {
    ...product,
    name: `${base} (copy)`,
    input_asset_path: product.input_asset_path,
    input_asset_paths: [...(product.input_asset_paths || [])],
  }
}

function pathKey(path: string) {
  return path.replace(/\\/g, '/').toLowerCase()
}

/** All product image paths currently attached to any product (hero + refs). */
export function collectProductImagePaths(products: Product[]): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const p of products) {
    for (const path of [p.input_asset_path, ...(p.input_asset_paths || [])]) {
      if (!path) continue
      const key = pathKey(path)
      if (seen.has(key)) continue
      seen.add(key)
      out.push(path)
    }
  }
  return out
}

function stripPathFromProduct(product: Product, path: string): Product {
  const key = pathKey(path)
  const hero =
    product.input_asset_path && pathKey(product.input_asset_path) === key
      ? null
      : product.input_asset_path
  const refs = (product.input_asset_paths || []).filter((p) => pathKey(p) !== key)
  return { ...product, input_asset_path: hero, input_asset_paths: refs }
}

/** Assign a path as hero for productIndex; remove it from every other product. */
export function assignProductHero(
  products: Product[],
  productIndex: number,
  path: string | null,
): Product[] {
  return products.map((p, i) => {
    let next = path ? stripPathFromProduct(p, path) : p
    if (i === productIndex) {
      next = { ...next, input_asset_path: path }
    }
    return next
  })
}

/** Toggle a path as an extra ref on productIndex; exclusive across products. */
export function toggleProductRef(
  products: Product[],
  productIndex: number,
  path: string,
  on: boolean,
): Product[] {
  return products.map((p, i) => {
    let next = stripPathFromProduct(p, path)
    if (i === productIndex && on) {
      const refs = [...(next.input_asset_paths || [])]
      if (!refs.some((r) => pathKey(r) === pathKey(path))) refs.push(path)
      next = { ...next, input_asset_paths: refs }
    }
    return next
  })
}
