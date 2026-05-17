---
layout: home
permalink: /
title: "Ruihan Yu"
author_profile: false
redirect_from:
  - /about/
  - /about.html
---

<section id="about" class="sect-lane">
  <div class="hero">
    <div class="hero__text">
      <h1 class="hero__name">Ruihan Yu <span style="font-weight:400;color:var(--color-muted);font-size:1.4rem;">Ryan</span></h1>
      <p class="hero__tagline">Working on 3D vision and rendering related topics.</p>
      <div class="hero__bio">
        <p>
          I am an <strong>M2 student</strong> in
          <a href="https://cgenglab.github.io/en/"><strong>Umetani Lab</strong></a>
          at <strong>The University of Tokyo</strong>.
          Before that, I received a B.S. in
          <strong>Physics and Mathematics</strong> from the
          Department of Physics, <strong>Tsinghua University</strong>.
        </p>
        <p>
          I am fortunate to collaborate with Prof.
          <a href="http://xufeng.site/"><strong>Feng Xu</strong></a>
          (Tsinghua University) and Prof.
          <a href="https://shuangz.com/"><strong>Shuang Zhao</strong></a>
          (University of Illinois Urbana-Champaign), and to have had a
          wonderful internship under Prof.
          <a href="https://www.haosu.ai/"><strong>Hao Su</strong></a>
          at UC San Diego.
        </p>
        <p>
          My long-term goal is to build faithful <strong>digital twins</strong> of
          the real world (you can call them <em>world models</em>, of course
          &mdash; a term that is kind of abused today) &mdash; representations we
          can not only render and reconstruct, but also <em>act on</em> to
          understand and feed back into the physical world. I work on
          <strong>video models</strong>, <strong>3D generation</strong>,
          <strong>physics-based / differentiable rendering</strong>, and
          <strong>neural scene representations</strong>, and I'm broadly interested
          in <strong>simulation</strong> and <strong>robotics</strong>.
        </p>
        <p>
          <strong>I am currently looking for a PhD position</strong>
          &mdash; please feel free to reach out.
        </p>
      </div>
      <p class="hero__contact">
        email&nbsp;&nbsp;auroraryan0301 at gmail dot com
      </p>
    </div>
    <div class="hero__photo">
      <img src="{{ '/images/profile.jpg' | relative_url }}" alt="Ruihan Yu">
    </div>
  </div>
</section>

<section id="publications" class="sect-lane sect-lane--frag">
  <h2 class="subhead">Selected Publications</h2>
  <div class="pub-list">

    <article class="pub">
      <div class="pub__thumb">
        <img src="{{ '/images/sample_matching_thumb.jpg' | relative_url }}" alt="Sample Matching teaser (Ours panel)">
      </div>
      <div class="pub__body">
        <h3 class="pub__title">Sample Matching for Joint Extinction Gradient Estimation in Differentiable Volume Rendering</h3>
        <p class="pub__authors">
          {% include author.html id="ruihan_yu" me=true %},
          {% include author.html id="yu_chen_wang" %},
          {% include author.html id="jingwang_ling" %},
          {% include author.html id="feng_xu" %},
          {% include author.html id="shuang_zhao" %}
        </p>
        <p class="pub__venue">ACM Transactions on Graphics (TOG), 2026</p>
        <p class="pub__award">
          <span class="pub__award-icon" aria-hidden="true">&#x1F3C6;</span>
          <span class="pub__award-text">Best papers award honorable mention</span>
        </p>
        <p class="pub__links">
          <a href="{{ '/samplematching/' | relative_url }}">project page</a>
          <a href="#">paper (soon)</a>
          <a href="#">code (soon)</a>
        </p>
      </div>
    </article>

    <article class="pub">
      <div class="pub__thumb">
        <img src="{{ '/images/gwr_thumb.png' | relative_url }}" alt="Generative World Renderer — Ours visual condition (snowy weather)">
      </div>
      <div class="pub__body">
        <h3 class="pub__title">Generative World Renderer</h3>
        <p class="pub__authors">
          {% include author.html id="zheng_hui_huang" %},
          {% include author.html id="zhixiang_wang" %},
          {% include author.html id="jiaming_tan" %},
          {% include author.html id="ruihan_yu" me=true %},
          {% include author.html id="yidan_zhang" %},
          {% include author.html id="bo_zheng" %},
          {% include author.html id="yu_lun_liu" %},
          {% include author.html id="yung_yu_chuang" %},
          {% include author.html id="kaipeng_zhang" %}
        </p>
        <p class="pub__venue">arXiv preprint, 2026</p>
        <p class="pub__links">
          <a href="https://arxiv.org/abs/2604.02329">arXiv</a>
          <a href="https://github.com/ShandaAI/AlayaRenderer">code (AlayaRenderer)</a>
        </p>
      </div>
    </article>

    <article class="pub">
      <div class="pub__thumb">
        <img src="{{ '/images/2dgh_thumb.png' | relative_url }}" alt="2DGH triangle fitting comparison">
      </div>
      <div class="pub__body">
        <h3 class="pub__title">2DGH: 2D Gaussian-Hermite Splatting for High-quality Rendering and Better Geometry Features</h3>
        <p class="pub__authors">
          {% include author.html id="ruihan_yu" me=true eq=true %},
          {% include author.html id="tianyu_huang" eq=true %},
          {% include author.html id="jingwang_ling" %},
          {% include author.html id="feng_xu" %}
        </p>
        <p class="pub__venue">IEEE Transactions on Visualization and Computer Graphics (TVCG), 2025</p>
        <p class="pub__links">
          <a href="{{ '/2dgh/' | relative_url }}">project page</a>
          <a href="https://ieeexplore.ieee.org/document/11204833/">IEEE</a>
          <a href="https://arxiv.org/abs/2408.16982">arXiv</a>
          <a href="#">code (soon)</a>
        </p>
      </div>
    </article>

    <article class="pub">
      <div class="pub__thumb">
        <img src="{{ '/images/nerf_emitter.gif' | relative_url }}" alt="NeRF as a Non-Distant Environment Emitter">
      </div>
      <div class="pub__body">
        <h3 class="pub__title">NeRF as a Non-Distant Environment Emitter in Physics-based Inverse Rendering</h3>
        <p class="pub__authors">
          {% include author.html id="jingwang_ling" %},
          {% include author.html id="ruihan_yu" me=true %},
          {% include author.html id="feng_xu" %},
          {% include author.html id="chun_du" %},
          {% include author.html id="shuang_zhao" %}
        </p>
        <p class="pub__venue">ACM SIGGRAPH 2024 (Conference Track)</p>
        <p class="pub__links">
          <a href="https://nerfemitterpbir.github.io/">project page</a>
          <a href="https://arxiv.org/abs/2402.04829">arXiv</a>
          <a href="https://github.com/gerwang/nerf-emitter">code</a>
        </p>
      </div>
    </article>

  </div>
</section>
