import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import '../styles/landing-page.css'
import { staticResidentPortraitUrl } from '../game/residentSpriteRuntime'

const RESIDENTS = [
  { name: '伊莎贝拉', trait: '把每次相遇写进记忆', src: staticResidentPortraitUrl('伊莎贝拉') },
  { name: '亚瑟', trait: '在学园区继续研究', src: staticResidentPortraitUrl('亚瑟') },
  { name: '卡门', trait: '会主动寻找新的关系', src: staticResidentPortraitUrl('卡门') },
  { name: '山本百合子', trait: '按自己的作息生活', src: staticResidentPortraitUrl('山本百合子') },
  { name: '弗朗西斯科', trait: '从经历中改变性格', src: staticResidentPortraitUrl('弗朗西斯科') },
  { name: '塔玛拉', trait: '与其他居民共享事件', src: staticResidentPortraitUrl('塔玛拉') },
] as const

const HERO_RESIDENTS = [
  { src: staticResidentPortraitUrl('伊莎贝拉'), className: 'hero-resident--one' },
  { src: staticResidentPortraitUrl('亚瑟'), className: 'hero-resident--two' },
  { src: staticResidentPortraitUrl('山本百合子'), className: 'hero-resident--three' },
  { src: staticResidentPortraitUrl('塔玛拉'), className: 'hero-resident--four' },
] as const

const MEMORY_LAYERS = [
  { index: '01', title: '事件记忆', copy: '记住一次谈话、一场争执，或你在街角留下的选择。' },
  { index: '02', title: '关系记忆', copy: '把反复发生的互动沉淀成信任、距离与立场。' },
  { index: '03', title: '反思记忆', copy: '从经历中形成判断，让下一次行动不再只是重复。' },
] as const

function MenuIcon({ open }: { open: boolean }) {
  return (
    <span className="site-menu-icon" data-open={open} aria-hidden="true">
      <span />
      <span />
    </span>
  )
}

export function LandingPage() {
  const [menuOpen, setMenuOpen] = useState(false)
  const [scrolled, setScrolled] = useState(false)
  const [compactNav, setCompactNav] = useState(
    () => window.matchMedia?.('(max-width: 1100px)').matches ?? false,
  )
  const menuButtonRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    document.body.classList.add('marketing-page-open')
    const updateHeader = () => setScrolled(window.scrollY > 24)
    updateHeader()
    window.addEventListener('scroll', updateHeader, { passive: true })

    const revealTargets = document.querySelectorAll<HTMLElement>('[data-reveal]')
    if (!('IntersectionObserver' in window) || window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
      revealTargets.forEach((target) => target.classList.add('is-visible'))
      return () => {
        document.body.classList.remove('marketing-page-open')
        window.removeEventListener('scroll', updateHeader)
      }
    }

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-visible')
            observer.unobserve(entry.target)
          }
        })
      },
      { threshold: 0.14 },
    )
    revealTargets.forEach((target) => observer.observe(target))

    return () => {
      document.body.classList.remove('marketing-page-open')
      window.removeEventListener('scroll', updateHeader)
      observer.disconnect()
    }
  }, [])

  useEffect(() => {
    const media = window.matchMedia?.('(max-width: 1100px)')
    if (!media) return
    const handleChange = (event: MediaQueryListEvent) => {
      setCompactNav(event.matches)
      if (!event.matches) setMenuOpen(false)
    }
    media.addEventListener('change', handleChange)
    return () => media.removeEventListener('change', handleChange)
  }, [])

  useEffect(() => {
    if (!menuOpen) return
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setMenuOpen(false)
        menuButtonRef.current?.focus()
      }
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [menuOpen])

  const closeMenu = () => setMenuOpen(false)

  return (
    <div className="marketing-site" id="top">
      <header className="site-header" data-scrolled={scrolled}>
        <Link className="site-brand" to="/" aria-label="Simverse World 首页" onClick={closeMenu}>
          <span className="site-brand__mark" aria-hidden="true">S/</span>
          <span className="site-brand__name">SIMVERSE</span>
        </Link>

        <nav
          className="site-nav"
          data-open={menuOpen}
          aria-label="官网导航"
          aria-hidden={compactNav && !menuOpen}
          inert={compactNav && !menuOpen ? true : undefined}
        >
          <a href="#world" onClick={closeMenu}>世界</a>
          <a href="#residents" onClick={closeMenu}>居民</a>
          <a href="#forge" onClick={closeMenu}>锻造</a>
          <a href="#memory" onClick={closeMenu}>记忆</a>
          <Link to="/town" onClick={closeMenu}>观察小镇</Link>
          <Link className="site-nav__mobile-entry" to="/login" onClick={closeMenu}>进入世界</Link>
        </nav>

        <div className="site-header__actions">
          <Link className="site-header__login" to="/login">登录</Link>
          <button
            ref={menuButtonRef}
            className="site-menu-button"
            type="button"
            aria-label={menuOpen ? '关闭导航菜单' : '打开导航菜单'}
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((open) => !open)}
          >
            <MenuIcon open={menuOpen} />
          </button>
        </div>
      </header>

      <main>
        <section className="site-hero" aria-labelledby="hero-title">
          <img
            className="site-hero__backdrop"
            src="/marketing/world-hero.jpg"
            alt=""
            fetchPriority="high"
          />
          <div className="site-hero__shade" />
          <div className="site-hero__content">
            <p className="site-kicker site-kicker--light">Persistent AI World / Live Beta</p>
            <h1 className="site-hero__title" id="hero-title" aria-label="Simverse World">
              <span>SIMVERSE</span>
              <span>WORLD</span>
            </h1>
            <p className="site-hero__lead">你离开后，小镇仍在生活；你回来后，每个选择都会留下痕迹。</p>
            <div className="site-hero__actions">
              <Link className="site-button site-button--primary" to="/login?next=%2Ftoday">
                看看今天发生了什么 <span aria-hidden="true">-&gt;</span>
              </Link>
              <Link className="site-button site-button--ghost" to="/town">观看小镇实况</Link>
            </div>
          </div>

          <div className="site-hero__residents" aria-hidden="true">
            {HERO_RESIDENTS.map((resident) => (
              <img
                className={`hero-resident ${resident.className}`}
                src={resident.src}
                alt=""
                key={resident.src}
              />
            ))}
          </div>

          <div className="site-hero__index" aria-hidden="true">
            <span>001</span>
            <span>THE CITY IS ALREADY AWAKE</span>
          </div>
        </section>

        <section className="world-section" id="world">
          <div className="section-shell world-section__intro" data-reveal>
            <p className="site-kicker">01 / WORLD</p>
            <h2 className="display-heading">这里没有等待触发的剧本，<br />只有正在发生的生活。</h2>
            <p className="section-lead">
              居民会移动、工作、交谈和反思。你离线之后，关系仍在变化，新的记忆仍在形成，城市不会为任何人按下暂停。
            </p>
          </div>

          <figure className="world-media" data-reveal>
            <img src="/marketing/world-map.jpg" alt="Simverse World 的像素城市地图" loading="lazy" />
            <figcaption>
              <span>LIVE WORLD MAP</span>
              <span>自由区 / 工程区 / 学园区 / 产品街区</span>
            </figcaption>
          </figure>
        </section>

        <section className="resident-section" id="residents">
          <div className="section-shell" data-reveal>
            <p className="site-kicker">02 / RESIDENTS</p>
            <h2 className="display-heading display-heading--dark">不是 NPC。<br />是会记住你的人。</h2>
          </div>

          <div className="resident-roster" data-reveal>
            {RESIDENTS.map((resident) => (
              <article className="resident-profile" key={resident.name}>
                <img src={resident.src} alt={`${resident.name} 的像素头像`} loading="lazy" />
                <div>
                  <h3>{resident.name}</h3>
                  <p>{resident.trait}</p>
                </div>
              </article>
            ))}
          </div>

          <div className="resident-stats section-shell" data-reveal>
            <div><strong>15</strong><span>维人格坐标驱动选择</span></div>
            <div><strong>14</strong><span>种自主行为持续运行</span></div>
            <div><strong>24/7</strong><span>世界循环不因离线停止</span></div>
          </div>
        </section>

        <section className="memory-section" id="memory">
          <div className="section-shell memory-section__layout">
            <div className="memory-section__copy" data-reveal>
              <p className="site-kicker site-kicker--light">03 / MEMORY</p>
              <h2 className="display-heading">经历留下痕迹，<br />痕迹改变下一次相遇。</h2>
              <p className="section-lead section-lead--light">
                三层记忆系统把瞬间、关系和反思连接起来。居民不是在重复回答，而是在携带过去继续生活。
              </p>
            </div>

            <ol className="memory-layers" data-reveal>
              {MEMORY_LAYERS.map((layer) => (
                <li key={layer.index}>
                  <span className="memory-layers__index">{layer.index}</span>
                  <div>
                    <h3>{layer.title}</h3>
                    <p>{layer.copy}</p>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section className="forge-section" id="forge">
          <div className="section-shell forge-section__heading" data-reveal>
            <p className="site-kicker">04 / FORGE</p>
            <h2 className="display-heading display-heading--dark">给一个名字。<br />锻造一位居民。</h2>
            <p className="section-lead section-lead--dark">
              从一句想法到完整的能力、人格与灵魂档案。快速锻造负责灵感，深度蒸馏负责把复杂的人带进世界。
            </p>
          </div>

          <div className="forge-media" data-reveal>
            <figure>
              <img src="/marketing/forge-guided.jpg" alt="引导式居民锻造界面" loading="lazy" />
              <figcaption><span>GUIDED FORGE</span><span>边聊边完成角色轮廓</span></figcaption>
            </figure>
            <figure>
              <img src="/marketing/forge-deep.jpg" alt="深度居民蒸馏界面" loading="lazy" />
              <figcaption><span>DEEP FORGE</span><span>研究、提取、验证与精炼</span></figcaption>
            </figure>
          </div>
        </section>

        <section className="life-loop-section">
          <div className="section-shell" data-reveal>
            <p className="site-kicker">THE LIVING LOOP</p>
            <h2 className="display-heading display-heading--dark">相遇。记住。演化。</h2>
            <div className="life-loop">
              <div><span>01</span><h3>相遇</h3><p>进入街区，与一个拥有自己目标的居民说话。</p></div>
              <div><span>02</span><h3>记住</h3><p>对话沉入事件与关系，成为下一次选择的上下文。</p></div>
              <div><span>03</span><h3>演化</h3><p>长期经历推动人格变化，世界因此产生真正的历史。</p></div>
            </div>
          </div>
        </section>

        <section className="final-callout">
          <img className="final-callout__backdrop" src="/marketing/world-map.jpg" alt="" loading="lazy" />
          <div className="final-callout__shade" />
          <div className="section-shell final-callout__content" data-reveal>
            <p className="site-kicker site-kicker--light">YOUR STORY STARTS MID-SCENE</p>
            <h2 className="display-heading">世界不会等你上线。</h2>
            <p>现在进入，看看居民们已经把今天过成了什么样子。</p>
            <Link className="site-button site-button--primary" to="/login">
              进入 Simverse <span aria-hidden="true">-&gt;</span>
            </Link>
          </div>
        </section>
      </main>

      <footer className="site-footer">
        <div className="site-footer__brand">
          <span className="site-brand__mark" aria-hidden="true">S/</span>
          <strong>SIMVERSE WORLD</strong>
          <p>一座由 AI 居民持续生活的开放世界。</p>
        </div>
        <div className="site-footer__links">
          <div><span>WORLD</span><a href="#world">城市</a><a href="#residents">居民</a><a href="#memory">记忆</a></div>
          <div><span>CREATE</span><a href="#forge">锻造</a><Link to="/login">登录</Link></div>
        </div>
        <div className="site-footer__meta">
          <span>SIMVERSE WORLD / 2026</span>
          <a href="#top">回到顶部</a>
        </div>
      </footer>
    </div>
  )
}
